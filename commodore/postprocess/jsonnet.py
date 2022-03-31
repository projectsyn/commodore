import json
import os
import functools

from pathlib import Path as P
from typing import Any, Callable, Dict, Iterable

import _jsonnet

from commodore.config import Config
from commodore.component import Component
from commodore.helpers import yaml_load, yaml_load_all, yaml_dump, yaml_dump_all
from commodore import __install_dir__


def _try_path(basedir: P, rel: str):
    """
    Returns content of file basedir/rel if it exists, None if file not found, or throws an exception
    """
    if not rel:
        raise RuntimeError("Got invalid filename (empty string).")
    if rel[0] == "/":
        full_path = P(rel)
    else:
        full_path = basedir / rel
    if full_path.is_dir():
        raise RuntimeError("Attempted to import a directory")

    if not full_path.is_file():
        return full_path.name, None
    with open(full_path, encoding="utf-8") as f:
        return full_path.name, f.read()


def _import_callback_with_searchpath(search: Iterable[P], basedir: P, rel: str):
    full_path, content = _try_path(basedir, rel)
    if content:
        return full_path, content
    for p in search:
        full_path, content = _try_path(p, rel)
        if content:
            return full_path, content
    raise RuntimeError("File not found")


def _import_cb(work_dir: P, basedir: str, rel: str):
    # Add current working dir to search path for Jsonnet import callback
    search_path = [
        work_dir.resolve(),
        __install_dir__.resolve(),
        (work_dir / "vendor").resolve(),
    ]
    return _import_callback_with_searchpath(search_path, P(basedir), rel)


def _list_dir(basedir: os.PathLike, basename: bool):
    """
    Non-recursively list files in directory `basedir`. If `basename` is set to
    True, only return the file name itself and not the full path.
    """
    files = [x for x in P(basedir).iterdir() if x.is_file()]

    if basename:
        return [f.parts[-1] for f in files]

    return files


_native_callbacks = {
    "yaml_load": (("file",), yaml_load),
    "yaml_load_all": (("file",), yaml_load_all),
    "list_dir": (
        (
            "dir",
            "basename",
        ),
        _list_dir,
    ),
}


def write_jsonnet_output(output_dir: P, output: str):
    out_objs = json.loads(output)
    for outobj, outcontents in out_objs.items():
        outpath = output_dir / f"{outobj}.yaml"
        if not outpath.exists():
            print(f"   > {outpath} doesn't exist, creating...")
            os.makedirs(outpath.parent, exist_ok=True)
        if isinstance(outcontents, list):
            yaml_dump_all(outcontents, outpath)
        else:
            yaml_dump(outcontents, outpath)


# pylint: disable=too-many-arguments
def jsonnet_runner(
    work_dir: P,
    inv: Dict[str, Any],
    component: str,
    instance: str,
    path: os.PathLike,
    jsonnet_func: Callable,
    jsonnet_input: os.PathLike,
    **kwargs: str,
):
    def _inventory() -> Dict[str, Any]:
        return inv

    _native_cb = _native_callbacks
    _native_cb["commodore_inventory"] = ((), _inventory)
    kwargs["target"] = component
    kwargs["component"] = component
    output_dir = work_dir / "compiled" / instance / path
    kwargs["output_path"] = str(output_dir)
    output = jsonnet_func(
        str(jsonnet_input),
        import_callback=functools.partial(_import_cb, work_dir),
        native_callbacks=_native_cb,
        ext_vars=kwargs,
    )
    write_jsonnet_output(output_dir, output)


def _filter_file(component: Component, filterpath: str) -> P:
    return component.target_directory / filterpath


def run_jsonnet_filter(
    config: Config,
    inv: Dict,
    component: Component,
    instance: str,
    filterid: str,
    path: P,
    **filterargs: str,
):
    """
    Run user-supplied jsonnet as postprocessing filter. This is the original
    way of doing postprocessing filters.
    """
    filterfile = _filter_file(component, filterid)
    # pylint: disable=c-extension-no-member
    jsonnet_runner(
        config.work_dir,
        inv,
        component.name,
        instance,
        path,
        _jsonnet.evaluate_file,
        filterfile,
        **filterargs,
    )


# pylint: disable=unused-argument
def validate_jsonnet_filter(config: Config, c: Component, instance: str, fd: Dict):
    filterfile = _filter_file(c, fd["filter"])
    if not filterfile.is_file():
        raise ValueError("Jsonnet filter definition does not exist")
