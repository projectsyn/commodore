import os
import json
from pathlib import Path as P
from subprocess import call  # nosec
from typing import Dict, Iterable, List, Optional, Tuple

import click

from . import git
from .config import Config
from .component import Component, component_dir
from .helpers import relsymlink, kapitan_inventory


def create_component_symlinks(cfg, component: Component):
    """
    Create symlinks in the inventory subdirectory.

    The actual code for components lives in the dependencies/ subdirectory, but
    we want to access some of the file contents through the inventory.
    """
    relsymlink(component.class_file, cfg.inventory.components_dir)
    inventory_default = cfg.inventory.defaults_file(component)
    relsymlink(
        component.defaults_file,
        inventory_default.parent,
        dest_name=inventory_default.name,
    )

    for file in component.lib_files:
        if cfg.debug:
            click.echo(f"     > installing template library: {file}")
        relsymlink(file, cfg.inventory.lib_dir)


def _discover_components(cfg) -> Tuple[List[str], Dict[str, str]]:
    """
    Discover components in `inventory_path/` by extracting all entries from
    the reclass applications dictionary.
    """
    kapitan_applications = kapitan_inventory(cfg, key="applications")
    components = set()
    component_aliases: Dict[str, str] = {}
    for component in kapitan_applications.keys():
        try:
            cn, alias = component.split(" as ")
        except ValueError:
            cn = component
            alias = component
        if cfg.debug:
            msg = f"   > Found component {cn}"
            if alias != component:
                msg += f" aliased to {alias}"
            click.echo(msg)
        components.add(cn)

        if alias in component_aliases:
            pc = component_aliases[alias]
            raise KeyError(
                f"Duplicate component alias {alias}: component {pc} is already aliased to {alias}"
            )
        component_aliases[alias] = cn

    return sorted(components), component_aliases


def _read_components(
    cfg: Config, component_names
) -> Tuple[Dict[str, str], Dict[str, Optional[str]]]:
    component_urls = {}
    component_versions = {}

    inv = kapitan_inventory(cfg)
    cluster_inventory = inv[cfg.inventory.bootstrap_target]
    components = cluster_inventory["parameters"].get("components", None)
    if not components:
        raise click.ClickException("Component list ('parameters.components') missing")

    for component_name in component_names:
        if component_name not in components:
            raise click.ClickException(
                f"Unknown component '{component_name}'. Please add it to 'parameters.components'"
            )

        info = components[component_name]

        if "url" not in info:
            raise click.ClickException(
                f"No url for component '{component_name}' configured"
            )

        component_urls[component_name] = info["url"]
        if cfg.debug:
            click.echo(f" > URL for {component_name}: {component_urls[component_name]}")
        if "version" in info:
            component_versions[component_name] = info["version"]
        else:
            # Note: We use version=None as a marker for checking out the remote repo's default branch
            component_versions[component_name] = None
        if cfg.debug:
            click.echo(
                f" > Version for {component_name}: {component_versions[component_name]}"
            )

    return component_urls, component_versions


def fetch_components(cfg: Config):
    """
    Download all components required by target. Generate list of components
    by searching for classes with prefix `components.` in the inventory files.

    Component repos are searched in `GLOBAL_GIT_BASE/commodore_components`.
    """

    click.secho("Discovering components...", bold=True)
    cfg.inventory.ensure_dirs()
    component_names, component_aliases = _discover_components(cfg)
    click.secho("Registering component aliases...", bold=True)
    cfg.register_component_aliases(component_aliases)
    urls, versions = _read_components(cfg, component_names)
    click.secho("Fetching components...", bold=True)
    for cn in component_names:
        if cfg.debug:
            click.echo(f" > Fetching component {cn}...")
        c = Component(
            cn, work_dir=cfg.work_dir, repo_url=urls[cn], version=versions[cn]
        )
        c.checkout()
        cfg.register_component(c)
        create_component_symlinks(cfg, c)


def fetch_jsonnet_libs(config: Config, libs):
    """
    Download all libraries specified in list `libs`.
    Each entry in `libs` is assumed to be a dict with keys
      * 'repository', the value of which is interpreted as a git repository to
                      clone.
      * 'files', a list of dicts which defines which files in the repository
                 should be installed as template libraries.
    Each entry in files is assumed to have the keys
      * 'libfile', indicating a filename relative to the repository of the
                   library to install
      * 'targetfile', the file name to use as the symlink target when
                      installing the library
    """

    click.secho("Updating Jsonnet libraries...", bold=True)
    config.inventory.ensure_dirs()
    for lib in libs:
        libname = lib["name"]
        if config.debug:
            filestext = " ".join([f["targetfile"] for f in lib["files"]])
            click.echo(f" > {libname}: {filestext}")
        library_dir = config.inventory.libs_dir / libname
        git.clone_repository(lib["repository"], library_dir, config)
        for file in lib["files"]:
            relsymlink(
                library_dir / file["libfile"],
                config.inventory.lib_dir,
                dest_name=file["targetfile"],
            )


def jsonnet_dependencies(config: Config) -> Iterable:
    """
    Creates a list of Jsonnet dependencies for the given Components.
    """
    dependencies = []

    for component in config.get_components().values():
        dependencies.append(
            {
                "source": {
                    "local": {
                        "directory": os.path.relpath(
                            component.target_directory, start=config.work_dir
                        ),
                    }
                }
            }
        )

    # Defining the `lib` folder as a local dependency is just a cheap way to have a symlink to that folder.
    dependencies.append(
        {
            "source": {
                "local": {
                    "directory": os.path.relpath(
                        config.inventory.lib_dir, start=config.work_dir
                    ),
                }
            }
        }
    )

    return dependencies


def write_jsonnetfile(file: P, deps: Iterable):
    """
    Writes the file `jsonnetfile.json` containing all provided dependencies.
    """
    data = {
        "version": 1,
        "dependencies": deps,
        "legacyImports": True,
    }

    with open(file, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, indent=4))


def fetch_jsonnet_libraries(cwd: P, deps: Iterable = None):
    """
    Download Jsonnet libraries using Jsonnet-Bundler.
    """
    jsonnetfile = cwd / "jsonnetfile.json"
    if not jsonnetfile.exists() or deps:
        if not deps:
            deps = []
        write_jsonnetfile(jsonnetfile, deps)

    inject_essential_libraries(jsonnetfile)

    try:
        # To make sure we don't use any stale lock files
        lock_file = cwd / "jsonnetfile.lock.json"
        if lock_file.exists():
            lock_file.unlink()
        if call(["jb", "install"], cwd=cwd) != 0:
            raise click.ClickException("jsonnet-bundler exited with error")
    except FileNotFoundError as e:
        raise click.ClickException(
            "the jsonnet-bundler executable `jb` could not be found"
        ) from e

    # Link essential libraries for backwards compatibility.
    lib_dir = (cwd / "vendor" / "lib").resolve()
    lib_dir.mkdir(exist_ok=True)
    relsymlink(
        cwd / "vendor" / "kube-libsonnet" / "kube.libsonnet", lib_dir, "kube.libjsonnet"
    )


def inject_essential_libraries(file: P):
    """
    Ensures essential libraries are added to `jsonnetfile.json`.
    :param file: The path to `jsonnetfile.json`.
    """
    with open(file, "r", encoding="utf-8") as f:
        data = json.load(f)

    deps = data["dependencies"]
    has_kube = False
    for dep in deps:
        remote = dep.get("source", {}).get("git", {}).get("remote", "")
        has_kube = has_kube or "kube-libsonnet" in remote

    if not has_kube:
        deps.append(
            {
                "source": {
                    "git": {"remote": "https://github.com/bitnami-labs/kube-libsonnet"}
                },
                "version": "v1.14.6",
            },
        )

    with open(file, "w", encoding="utf-8") as j:
        json.dump(data, j, indent=4)


def register_components(cfg: Config):
    """
    Discover components in the inventory, and register them if the
    corresponding directory in `dependencies/` exists.

    Create component symlinks for discovered components which exist.
    """
    click.secho("Discovering included components...", bold=True)
    components, component_aliases = _discover_components(cfg)
    click.secho("Registering components and aliases...", bold=True)

    for cn in components:
        if cfg.debug:
            click.echo(f" > Registering component {cn}...")
        if not component_dir(cfg.work_dir, cn).is_dir():
            click.secho(
                f" > Skipping registration of component {cn}: repo is not available",
                fg="yellow",
            )
            continue
        component = Component(cn, work_dir=cfg.work_dir)
        cfg.register_component(component)
        create_component_symlinks(cfg, component)

    registered_components = cfg.get_components().keys()
    pruned_aliases = {
        a: c for a, c in component_aliases.items() if c in registered_components
    }
    pruned = sorted(set(component_aliases.keys()) - set(pruned_aliases.keys()))
    if len(pruned) > 0:
        click.secho(
            f" > Dropping alias(es) {pruned} with missing component(s).", fg="yellow"
        )
    cfg.register_component_aliases(pruned_aliases)
