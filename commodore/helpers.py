from __future__ import annotations

import collections
import itertools
import json
import shutil
import os
import sys
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path as P
from typing import Optional

import click
import requests
import yaml

from enum import Enum

# pylint: disable=redefined-builtin
from requests.exceptions import ConnectionError, HTTPError
from kapitan import cached
from kapitan import targets as kapitan_targets
from kapitan import defaults
from kapitan.cached import reset_cache as reset_reclass_cache
from kapitan.refs.base import RefController, PlainRef
from kapitan.refs.secrets.vaultkv import VaultBackend

from reclass_rs import Reclass

from commodore import __install_dir__
from commodore.config import Config
from commodore.normalize_url import normalize_url


ArgumentCache = collections.namedtuple(
    "ArgumentCache",
    [
        "inventory_backend",
        "inventory_path",
        "multiline_string_style",
        "yaml_dump_null_as_empty",
    ],
)


class FakeVaultBackend(VaultBackend):
    def __init__(self):
        "init FakeVaultBackend ref backend type"
        super().__init__(None)

    def __getitem__(self, ref_path):
        return PlainRef(ref_path)


class ApiError(Exception):
    pass


class IndentedListDumper(yaml.Dumper):
    """
    Dumper which preserves indentation of list items by overriding indentless.
    """

    def increase_indent(self, flow=False, *args, **kwargs):
        return super().increase_indent(flow=flow, indentless=False)


def yaml_load(file):
    """
    Load single-document YAML and return document
    """
    with open(file, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def yaml_load_all(file):
    """
    Load multi-document YAML and return documents in list
    """
    with open(file, "r", encoding="utf-8") as f:
        return list(yaml.safe_load_all(f))


def _represent_str(dumper, data):
    """
    Custom string rendering when dumping data as YAML.

    Hooking this method into PyYAML with

        yaml.add_representer(str, _represent_str)

    will configure the YAML dumper to render strings which contain newline
    characters as block scalars with the last newline stripped.
    """
    style = None
    if "\n" in data:
        style = "|"
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


def yaml_dump(obj, file):
    """
    Dump obj as single-document YAML
    """
    yaml.add_representer(str, _represent_str)
    with open(file, "w", encoding="utf-8") as outf:
        yaml.dump(obj, outf, Dumper=IndentedListDumper)


def yaml_dump_all(obj, file):
    """
    Dump obj as multi-document YAML
    """
    yaml.add_representer(str, _represent_str)
    with open(file, "w", encoding="utf-8") as outf:
        yaml.dump_all(obj, outf, Dumper=IndentedListDumper)


class RequestMethod(Enum):
    GET = "GET"
    POST = "POST"


def _lieutenant_request(
    method: RequestMethod,
    api_url: str,
    api_token: str,
    api_endpoint: str,
    api_id: str,
    params={},
    timeout=5,
    **kwargs,
):
    url = normalize_url(f"{api_url}/{api_endpoint}/{api_id}")
    headers = {"Authorization": f"Bearer {api_token}"}
    try:
        if method == RequestMethod.GET:
            r = requests.get(url, headers=headers, params=params, timeout=timeout)
        elif method == RequestMethod.POST:
            headers["Content-Type"] = "application/json"
            data = kwargs.get("post_data", {})
            r = requests.post(
                url,
                json.dumps(data),
                headers=headers,
                params=params,
                timeout=timeout,
                # don't let requests handle redirects (usually if the API URL is given without
                # https://), since requests will rewrite the method to GET for the redirect which
                # makes no sense when we're trying to POST to a POST-only endpoint.
                allow_redirects=False,
            )

            if r.status_code in [301, 302, 307, 308]:
                # Explicitly redo the POST if we get a 301, 302, 307 or 308 status code for the
                # first call. We don't validate that the redirect location has the same domain as
                # the original request, since we already unconditionally follow redirects  with the
                # bearer token for GET requests.
                # Note that this wouldn't be necessary if all Lieutenant APIs would redirect us with
                # a 308 for POST requests.
                r = requests.post(
                    r.headers["location"],
                    json.dumps(data),
                    headers=headers,
                    params=params,
                    timeout=timeout,
                )
        else:
            raise NotImplementedError(f"QueryType {method} not implemented")
    except ConnectionError as e:
        raise ApiError(f"Unable to connect to Lieutenant at {api_url}") from e
    except NotImplementedError as e:
        raise e

    return _handle_lieutenant_response(r)


def _handle_lieutenant_response(r: requests.Response):
    try:
        if r.text:
            resp = json.loads(r.text)
        else:
            resp = {}
    except json.JSONDecodeError as e:
        raise ApiError("Client error: Unable to parse JSON") from e
    try:
        r.raise_for_status()
    except HTTPError as e:
        extra_msg = "."
        if r.status_code >= 400:
            if "reason" in resp:
                extra_msg = f": {resp['reason']}"
            else:
                extra_msg = f": {e}"
        raise ApiError(f"API returned {r.status_code}{extra_msg}") from e
    else:
        return resp


def lieutenant_query(api_url, api_token, api_endpoint, api_id, params={}, timeout=5):
    return _lieutenant_request(
        RequestMethod.GET, api_url, api_token, api_endpoint, api_id, params, timeout
    )


def lieutenant_post(
    api_url, api_token, api_endpoint, api_id, post_data, params={}, timeout=5
):
    return _lieutenant_request(
        RequestMethod.POST,
        api_url,
        api_token,
        api_endpoint,
        api_id,
        params,
        timeout,
        post_data=post_data,
    )


def _verbose_rmtree(tree, *args, **kwargs):
    click.echo(f" > deleting {tree}/")
    shutil.rmtree(tree, *args, **kwargs)


def clean_working_tree(config: Config):
    # Defining rmtree as a naked Callable means that mypy won't complain about
    # _verbose_rmtree and shutil.rmtree having slightly different signatures.
    rmtree: Callable
    if config.debug:
        rmtree = _verbose_rmtree
    else:
        rmtree = shutil.rmtree
    click.secho("Cleaning working tree", bold=True)
    rmtree(config.inventory.inventory_dir, ignore_errors=True)
    rmtree(config.inventory.lib_dir, ignore_errors=True)
    rmtree(config.inventory.libs_dir, ignore_errors=True)
    rmtree(config.inventory.output_dir, ignore_errors=True)
    rmtree(config.catalog_dir, ignore_errors=True)


# pylint: disable=too-many-arguments
def kapitan_compile(
    config: Config,
    targets: Iterable[str],
    output_dir: Optional[P] = None,
    search_paths=None,
    fake_refs=False,
    reveal=False,
):
    if not output_dir:
        output_dir = config.work_dir

    if not search_paths:
        search_paths = []
    search_paths = search_paths + [
        config.work_dir,
        __install_dir__,
    ]
    reset_reclass_cache()
    refController = RefController(config.refs_dir)
    if fake_refs:
        refController.register_backend(FakeVaultBackend())
    click.secho("Compiling catalog...", bold=True)
    # workaround the non-modifiable Namespace() default value for cached.args
    cached.args.inventory_backend = "reclass-rs"
    cached.args.inventory_path = str(config.inventory.inventory_dir)
    cached.args.multiline_string_style = "literal"
    cached.args.yaml_dump_null_as_empty = False
    cached.args.verbose = config.trace
    cached.args.output_path = output_dir
    cached.args.targets = targets
    cached.args.parallelism = None
    cached.args.labels = None
    cached.args.prune = False
    cached.args.indent = 2
    cached.args.reveal = reveal
    cached.args.cache = False
    cached.args.cache_paths = None
    cached.args.fetch = config.fetch_dependencies
    # We always want to force-fetch when we want to fetch dependencies
    # XXX(sg): We need to set `force` because otherwise `compile_targets()` raises an exception
    # becaues the field is missing, but we can't set it to true, because otherwise
    # `compile_targets()` emits a deprecation warning.
    cached.args.force = False
    cached.args.force_fetch = config.fetch_dependencies
    cached.args.validate = False
    cached.args.schemas_path = config.work_dir / "schemas"
    cached.args.jinja2_filters = defaults.DEFAULT_JINJA2_FILTERS_PATH
    cached.args.use_go_jsonnet = True
    kapitan_targets.compile_targets(
        inventory_path=cached.args.inventory_path,
        search_paths=search_paths,
        ref_controller=refController,
        args=cached.args,
    )


def kapitan_inventory(
    config: Config, key: str = "nodes", ignore_class_notfound: bool = False
) -> dict:
    """
    Returns the top-level key according to the kwarg.
    """
    r = Reclass(
        nodes_path=str(config.inventory.targets_dir),
        classes_path=str(config.inventory.classes_dir),
        ignore_class_notfound=ignore_class_notfound,
    )
    print("running reclass_rs", file=sys.stderr)
    start = datetime.now()
    try:
        inv = r.inventory()
    except ValueError as e:
        raise click.ClickException(f"While rendering inventory: {e}")
    elapsed = datetime.now() - start
    print(f"Inventory (reclass_rs) took {elapsed}", file=sys.stderr)

    return inv.as_dict()[key]


def rm_tree_contents(basedir):
    """
    Delete all files in directory `basedir`, but do not delete the directory
    itself.
    """
    basedir = P(basedir)
    if not basedir.is_dir():
        raise ValueError("Expected directory as argument")
    for f in basedir.glob("*"):
        if f.name.startswith("."):
            # pathlib's glob doesn't filter hidden files, skip them here
            continue
        if f.is_dir():
            shutil.rmtree(f)
        else:
            os.unlink(f)


def relsymlink(src: P, dest_dir: P, dest_name: Optional[str] = None):
    if dest_name is None:
        dest_name = src.name
    # pathlib's relative_to() isn't suitable for this use case, since it only
    # works for dropping a path's prefix according to the documentation. See
    # https://docs.python.org/3/library/pathlib.html#pathlib.PurePath.relative_to
    link_src = os.path.relpath(src, start=dest_dir)
    link_dst = dest_dir / dest_name
    if not P(src).exists():
        raise click.ClickException(
            f"Can't link {link_src} to {link_dst}. Source does not exist."
        )
    if link_dst.exists() or link_dst.is_symlink():
        os.remove(link_dst)
    os.symlink(link_src, link_dst)


def sliding_window(iterable, n):
    # sliding_window('ABCDEFG', 4) -> ABCD BCDE CDEF DEFG
    it = iter(iterable)
    window = collections.deque(itertools.islice(it, n), maxlen=n)
    if len(window) == n:
        yield tuple(window)
    for x in it:
        window.append(x)
        yield tuple(window)
