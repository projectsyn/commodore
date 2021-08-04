import json

from pathlib import Path as P
from typing import Dict

import _jsonnet
import click

from commodore import __install_dir__
from commodore.config import Config
from commodore.component import Component

from .jsonnet import jsonnet_runner


def _output_dir(work_dir: P, compiled_dir: str, path):
    """Compute directory in which to apply filter"""
    return work_dir / "compiled" / compiled_dir / path


def _builtin_filter_helm_namespace(
    work_dir: P, inv, component: Component, path, **kwargs
):
    if "namespace" not in kwargs:
        raise click.ClickException(
            "Builtin filter 'helm_namespace': filter argument 'namespace' is required"
        )
    create_namespace = kwargs.get("create_namespace", "false")
    # Transform create_namespace to string as jsonnet extvars can only be
    # strings
    if isinstance(create_namespace, bool):
        create_namespace = "true" if create_namespace else "false"
    exclude_objects = kwargs.get("exclude_objects", [])
    exclude_objects = "|".join([json.dumps(e) for e in exclude_objects])
    # NOTE: we pass "" for compiled_dir here, as we already patch `path` to
    # contain the output dir in postprocess/__init__.py
    output_dir = _output_dir(work_dir, "", path)

    # pylint: disable=c-extension-no-member
    jsonnet_runner(
        work_dir,
        inv,
        component.name,
        path,
        _jsonnet.evaluate_file,
        __install_dir__ / "filters" / "helm_namespace.jsonnet",
        namespace=kwargs["namespace"],
        create_namespace=create_namespace,
        exclude_objects=exclude_objects,
        chart_output_dir=str(output_dir),
    )


_builtin_filters = {
    "helm_namespace": _builtin_filter_helm_namespace,
}


class UnknownBuiltinFilter(ValueError):
    def __init__(self, filtername):
        super().__init__(f"Unknown builtin filter: {filtername}")
        self.filtername = filtername


def run_builtin_filter(
    config: Config,
    inv: Dict,
    component: Component,
    filterid: str,
    path: P,
    **filterargs: str,
):
    if filterid not in _builtin_filters:
        raise UnknownBuiltinFilter(filterid)
    _builtin_filters[filterid](config.work_dir, inv, component, path, **filterargs)


def validate_builtin_filter(config: Config, c: Component, fd: Dict):
    if fd["filter"] not in _builtin_filters:
        raise UnknownBuiltinFilter(fd["filter"])

    if "filterargs" not in fd:
        raise KeyError("Builtin filter is missing required key 'filterargs'")

    compiled_dir = fd.get("output_dir", c.name)

    fpath = _output_dir(config.work_dir, compiled_dir, fd["path"])
    if not fpath.exists():
        raise ValueError("Builtin filter called on path which doesn't exist")
