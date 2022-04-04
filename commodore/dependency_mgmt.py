import os
import json
from pathlib import Path as P
from subprocess import call  # nosec
from typing import Any, Dict, Iterable, List, Optional, Tuple, Set

import click

from .config import Config
from .component import Component, component_dir
from .helpers import relsymlink, kapitan_inventory


def validate_component_library_name(cfg: Config, cname: str, lib: P) -> P:
    if not lib.stem.startswith(cname):
        deprecation_notice_url = (
            "https://syn.tools/commodore/reference/"
            + "deprecation-notices.html#_component_lib_naming"
        )
        cfg.register_deprecation_notice(
            f"Component '{cname}' uses component library name {lib.name} "
            + "which isn't prefixed with the component's name. "
            + f"See {deprecation_notice_url} for more details."
        )

    return lib


def _check_library_alias_prefixes(libalias: str, cn: str, component_prefixes: Set[str]):
    for p in component_prefixes - {cn}:
        if libalias.startswith(p):
            raise click.ClickException(
                f"Invalid alias prefix '{p}' "
                + f"for template library alias of component '{cn}'"
            )


def _check_library_alias_collisions(cfg: Config, cluster_params: Dict[str, Any]):
    # map of library alias to set(originating components)
    collisions: Dict[str, Set[str]] = {}

    components = cfg.get_components()
    component_prefixes = set(cluster_params["components"].keys())

    for cn, component in components.items():
        cmeta = cluster_params[component.parameters_key].get("_metadata", {})
        aliases = cmeta.get("library_aliases", {})
        for libalias in aliases.keys():
            _check_library_alias_prefixes(libalias, cn, component_prefixes)
            collisions.setdefault(libalias, set()).add(cn)

    for libalias, cnames in collisions.items():
        if len(cnames) > 1:
            clist = _format_component_list(cnames)
            _all = "all" if len(cnames) > 2 else "both"
            raise click.ClickException(
                f"Components {clist} {_all} define component library alias '{libalias}'"
            )


def create_component_library_aliases(cfg: Config, cluster_params: Dict[str, Any]):
    _check_library_alias_collisions(cfg, cluster_params)

    for _, component in cfg.get_components().items():
        cmeta = cluster_params[component.parameters_key].get("_metadata", {})
        aliases = cmeta.get("library_aliases", {}).items()

        for libalias, libname in aliases:
            if cfg.debug:
                click.echo(f"     > aliasing template library {libname} to {libalias}")
            libf = component.get_library(libname)
            if not libf:
                click.secho(
                    f" > [WARN] '{component.name}' template library alias '{libalias}' "
                    + f"refers to nonexistent template library '{libname}'",
                    fg="yellow",
                )
            else:
                relsymlink(libf, cfg.inventory.lib_dir, dest_name=libalias)


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
        relsymlink(
            validate_component_library_name(cfg, component.name, file),
            cfg.inventory.lib_dir,
        )


def _format_component_list(components: Iterable[str]) -> str:
    formatted_list = list(map(lambda c: f"'{c}'", sorted(components)))

    if len(formatted_list) == 0:
        return ""

    if len(formatted_list) == 1:
        return f"{formatted_list[0]}"

    formatted = ", ".join(formatted_list[:-1])

    # Use serial ("Oxford") comma when formatting lists of 3 or more items, cf.
    # https://en.wikipedia.org/wiki/Serial_comma
    serial_comma = ""
    if len(formatted_list) > 2:
        serial_comma = ","

    formatted += f"{serial_comma} and {formatted_list[-1]}"

    return formatted


def _discover_components(cfg) -> Tuple[List[str], Dict[str, str]]:
    """
    Discover components used by the currenct cluster by extracting all entries from the
    reclass applications dictionary.
    """
    kapitan_applications = kapitan_inventory(cfg, key="applications")
    components = set()
    all_component_aliases: Dict[str, Set[str]] = {}
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
        all_component_aliases.setdefault(alias, set()).add(cn)

    component_aliases: Dict[str, str] = {}

    for alias, cns in all_component_aliases.items():
        if len(cns) == 0:
            # NOTE(sg): This should never happen, but we add it for completeness' sake.
            raise ValueError(
                f"Discovered component alias '{alias}' with no associated components"
            )

        if len(cns) > 1:
            if alias in cns:
                other_aliases = list(cns - set([alias]))
                if len(other_aliases) > 1:
                    clist = _format_component_list(other_aliases)
                    raise KeyError(
                        f"Components {clist} alias existing component '{alias}'"
                    )

                # If this assertion fails we have a problem, since `other_aliases` is
                # the result of removing a single element from a set which contains
                # multiple elements and we've already handled the case for len() > 1.
                # Since we don't mind if it's optimized out in some cases, we annotate
                # it with `nosec` so bandit doesn't complain about it.
                assert len(other_aliases) == 1  # nosec
                raise KeyError(
                    f"Component '{other_aliases[0]}' "
                    + f"aliases existing component '{alias}'"
                )

            clist = _format_component_list(cns)
            raise KeyError(
                f"Duplicate component alias '{alias}': "
                + f"components {clist} are aliased to '{alias}'"
            )

        # len(cns) must be 1 here, as we already raise an Exception for len(cns) ==
        # 0 earlier. We still assert this condition here and annotate with `nosec`
        # so bandit doesn't complain about it.
        assert len(cns) == 1  # nosec
        component_aliases[alias] = list(cns)[0]

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
            cfg.register_deprecation_notice(
                f"Component {component_name} doesn't have a version specified. "
                + "See https://syn.tools/commodore/reference/deprecation-notices.html"
                + "#_components_without_versions for more details."
            )
            # Note: We use version=None as a marker for checking out the remote repo's
            # default branch.
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
        f.write("\n")


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
                "version": "v1.19.0",
            },
        )

    with open(file, "w", encoding="utf-8") as j:
        json.dump(data, j, indent=4)
        j.write("\n")


def register_components(cfg: Config):
    """
    Discover components in the inventory, and register them if the
    corresponding directory in `dependencies/` exists.

    Create component symlinks for discovered components which exist.
    """
    click.secho("Discovering included components...", bold=True)
    try:
        components, component_aliases = _discover_components(cfg)
    except KeyError as e:
        raise click.ClickException(f"While discovering components: {e}")
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


def verify_component_version_overrides(cluster_parameters):
    errors = []
    for cname, cspec in cluster_parameters["components"].items():
        if "url" not in cspec:
            errors.append(cname)

    if len(errors) > 0:
        cnames = _format_component_list(errors)
        s = "s" if len(errors) > 1 else ""
        have = "have" if len(errors) > 1 else "has"
        raise click.ClickException(
            f"Version override{s} specified for component{s} {cnames} which {have} no URL"
        )
