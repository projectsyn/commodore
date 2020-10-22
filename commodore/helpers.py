import collections
import json
import shutil
import os
from pathlib import Path as P
from typing import Callable, Iterable

import click
import requests
import yaml

# pylint: disable=redefined-builtin
from requests.exceptions import ConnectionError, HTTPError
from url_normalize import url_normalize
from kapitan import cached
from kapitan import targets as kapitan_targets
from kapitan import defaults
from kapitan.cached import reset_cache as reset_reclass_cache
from kapitan.refs.base import RefController, PlainRef
from kapitan.refs.secrets.vaultkv import VaultBackend

from commodore import __install_dir__
from commodore.config import Config


ArgumentCache = collections.namedtuple("ArgumentCache", ["inventory_path"])


class FakeVaultBackend(VaultBackend):
    def __init__(self):
        "init FakeVaultBackend ref backend type"
        super().__init__(None)

    def __getitem__(self, ref_path):
        return PlainRef(ref_path)


class ApiError(Exception):
    pass


def yaml_load(file):
    """
    Load single-document YAML and return document
    """
    with open(file, "r") as f:
        return yaml.safe_load(f)


def yaml_load_all(file):
    """
    Load multi-document YAML and return documents in list
    """
    with open(file, "r") as f:
        return list(yaml.safe_load_all(f))


def yaml_dump(obj, file):
    """
    Dump obj as single-document YAML
    """
    with open(file, "w") as outf:
        yaml.dump(obj, outf)


def yaml_dump_all(obj, file):
    """
    Dump obj as multi-document YAML
    """
    with open(file, "w") as outf:
        yaml.dump_all(obj, outf)


def lieutenant_query(api_url, api_token, api_endpoint, api_id):
    try:
        r = requests.get(
            url_normalize(f"{api_url}/{api_endpoint}/{api_id}"),
            headers={"Authorization": f"Bearer {api_token}"},
        )
    except ConnectionError as e:
        raise ApiError(f"Unable to connect to Lieutenant at {api_url}") from e
    try:
        resp = json.loads(r.text)
    except json.JSONDecodeError:
        resp = {"message": "Client error: Unable to parse JSON"}
    try:
        r.raise_for_status()
    except HTTPError as e:
        extra_msg = "."
        if r.status_code >= 400:
            extra_msg = f": {resp['reason']}"
        raise ApiError(f"API returned {r.status_code}{extra_msg}") from e
    else:
        return resp


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
    rmtree("inventory", ignore_errors=True)
    rmtree("dependencies", ignore_errors=True)
    rmtree("compiled", ignore_errors=True)
    rmtree("catalog", ignore_errors=True)


# pylint: disable=too-many-arguments
def kapitan_compile(
    config: Config,
    targets: Iterable[str],
    output_dir="./",
    search_paths=None,
    fake_refs=False,
    fetch_dependencies=True,
    reveal=False,
):
    if not search_paths:
        search_paths = []
    search_paths = search_paths + [
        "./",
        __install_dir__,
    ]
    reset_reclass_cache()
    refController = RefController("./catalog/refs")
    if fake_refs:
        refController.register_backend(FakeVaultBackend())
    click.secho("Compiling catalog...", bold=True)
    cached.args["compile"] = ArgumentCache(inventory_path="./inventory")
    kapitan_targets.compile_targets(
        inventory_path="./inventory",
        search_paths=search_paths,
        output_path=output_dir,
        targets=targets,
        parallel=4,
        labels=None,
        ref_controller=refController,
        verbose=config.trace,
        prune=False,
        indent=2,
        reveal=reveal,
        cache=False,
        cache_paths=None,
        fetch_dependencies=fetch_dependencies,
        validate=False,
        schemas_path="./schemas",
        jinja2_filters=defaults.DEFAULT_JINJA2_FILTERS_PATH,
    )


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


def relsymlink(srcdir, srcname, destdir, destname=None):
    if destname is None:
        destname = srcname
    # pathlib's relative_to() isn't suitable for this use case, since it only
    # works for dropping a path's prefix according to the documentation. See
    # https://docs.python.org/3/library/pathlib.html#pathlib.PurePath.relative_to
    link_src = os.path.relpath(P(srcdir) / srcname, start=destdir)
    link_dst = P(destdir) / destname
    if link_dst.exists():
        os.remove(link_dst)
    os.symlink(link_src, link_dst)


def delsymlink(linkname: P, debug=False):
    """
    A convenience function to remove a symlink.

    Ensures the target path actually exists and is a symlink before deleting, or
    noops.
    """

    # This will also be False in case it doesn't exist.
    if linkname.is_symlink():
        if debug:
            click.echo(f"Deleting symlink: {linkname}")
        linkname.unlink()
    else:
        if debug:
            click.echo(f"Trying to delete non-symlink path {linkname}. No deleting!")
