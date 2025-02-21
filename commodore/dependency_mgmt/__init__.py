from __future__ import annotations

import itertools
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Iterable

import click
from click import ClickException

from commodore.config import Config
from commodore.component import Component, component_dir
from commodore.gitrepo import RefError
from commodore.helpers import relsymlink
from commodore.package import Package, package_dependency_dir

from .component_library import validate_component_library_name
from .discovery import _discover_components, _discover_packages
from .tools import format_component_list
from .version_parsing import _read_components, _read_packages, DependencySpec


def create_component_symlinks(cfg, component: Component):
    """
    Create symlinks in the inventory subdirectory.

    The actual code for components lives in the dependencies/ subdirectory, but
    we want to access some of their files through the inventory.
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
            validate_component_library_name(component.name, file),
            cfg.inventory.lib_dir,
        )


def create_alias_symlinks(cfg, component: Component, alias: str):
    if not component.has_alias(alias):
        raise ValueError(
            f"component {component.name} doesn't have alias {alias} registered"
        )
    relsymlink(
        component.alias_class_file(alias),
        cfg.inventory.components_dir,
        dest_name=f"{alias}.yml",
    )
    inventory_default = cfg.inventory.defaults_file(alias)
    relsymlink(
        component.alias_defaults_file(alias),
        inventory_default.parent,
        dest_name=inventory_default.name,
    )


def create_package_symlink(cfg, pname: str, package: Package):
    """
    Create package symlink in the inventory.

    Packages are downloaded to `dependencies/pkg.{package-name}/{path}` and symlinked to
    `inventory/classes/{package-name}`.
    """
    if not package.target_dir:
        raise ValueError("Can't symlink package which doesn't have a working directory")
    if not package.target_dir.is_dir():
        raise ValueError(
            f"Can't symlink package subpath {package.sub_path}, not a directory"
        )
    relsymlink(package.target_dir, cfg.inventory.classes_dir, dest_name=pname)


def fetch_components(cfg: Config):
    """
    Download all components required by target.

    This function discovers required components by parsing key `applications` in the
    hierarchy.
    """

    click.secho("Discovering components...", bold=True)
    cfg.inventory.ensure_dirs()
    component_names, component_aliases = _discover_components(cfg)
    click.secho("Registering component aliases...", bold=True)
    cfg.register_component_aliases(component_aliases)
    cspecs = _read_components(cfg, component_aliases)
    click.secho("Fetching components...", bold=True)

    deps: dict[str, list] = {}
    for cn in component_names:
        cspec = cspecs[cn]
        if cfg.debug:
            click.echo(f" > Fetching component {cn}...")
        cdep = cfg.register_dependency_repo(cspec.url)
        c = Component(
            cn,
            work_dir=cfg.work_dir,
            dependency=cdep,
            version=cspec.version,
            sub_path=cspec.path,
        )
        if c.checkout_is_dirty() and not cfg.force:
            raise click.ClickException(
                f"Component {cn} has uncommitted changes. "
                + "Please specify `--force` to discard them"
            )
        deps.setdefault(cdep.url, []).append(c)
    do_parallel(fetch_component, cfg, deps.values())

    _setup_component_aliases(cfg, component_aliases, cspecs, set(deps.keys()))


def _setup_component_aliases(
    cfg: Config,
    component_aliases: dict[str, str],
    cspecs: dict[str, DependencySpec],
    component_urls: set[str],
):
    components = cfg.get_components()
    aliases: dict[str, list] = {}
    for alias, component in component_aliases.items():
        if alias == component:
            # Nothing to setup for identity alias
            continue

        c = components[component]
        aspec = cspecs[alias]
        adep = c.dependency
        if aspec.url != c.repo_url:
            adep = cfg.register_dependency_repo(aspec.url)
        c.register_alias(alias, aspec.version, adep, aspec.path)
        if c.alias_checkout_is_dirty(alias) and not cfg.force:
            raise click.ClickException(
                f"Component alias {alias} has uncommitted changes. "
                + "Please specify `--force` to discard them"
            )
        if adep.url in component_urls:
            # NOTE(sg): if we already processed the dependency URL in the previous fetch
            # stage, we can create all instance worktrees in parallel. We do so by using
            # the alias name as the key for our "parallelization" dict.
            aliases[alias] = [(alias, c)]
        else:
            # Otherwise, we use adep.url as the parallelization key to avoid any race
            # conditions when creating multiple worktrees from a not-yet-cloned
            # dependency URL.
            aliases.setdefault(adep.url, []).append((alias, c))

    do_parallel(setup_alias, cfg, aliases.values())


def fetch_component(cfg: Config, dependencies: Iterable[Component]):
    """
    Fetch all components of a MultiDependency object.
    """
    for c in dependencies:
        try:
            c.checkout()
        except RefError as e:
            raise ClickException(f"while fetching component {c.name}: {e}")
        cfg.register_component(c)
        create_component_symlinks(cfg, c)


def setup_alias(cfg: Config, aliases: Iterable[tuple[str, Component]]):
    for alias, c in aliases:
        try:
            c.checkout_alias(alias)
        except RefError as e:
            raise ClickException(f"while setting up component instance {alias}: {e}")
        create_alias_symlinks(cfg, c, alias)


def do_parallel(fun: Callable[[Config, Iterable], None], cfg: Config, data: Iterable):
    """
    Fetch dependencies in parallel threads with ThreadPoolExecutor.
    """
    with ThreadPoolExecutor() as exe:
        # We need to collect the results from the iterator produced by exe.map to ensure
        # that any exceptions raised in `fetch_fun` are propagated, cf.
        # https://docs.python.org/3/library/concurrent.futures.html#executor-objects. We
        # do so by simply materializing the iterator into a list.
        list(exe.map(fun, itertools.repeat(cfg), data))


def register_components(cfg: Config):
    """
    Discover components in the inventory, and register them if the
    corresponding directory in `dependencies/` exists.

    Create component symlinks for discovered components which exist.
    """
    click.secho("Discovering included components...", bold=True)
    try:
        components, component_aliases = _discover_components(cfg)
        cspecs = _read_components(cfg, component_aliases)
    except KeyError as e:
        raise click.ClickException(f"While discovering components: {e}")
    click.secho("Registering components and aliases...", bold=True)

    for cn in components:
        cspec = cspecs[cn]
        if cfg.debug:
            click.echo(f" > Registering component {cn}...")
        if not component_dir(cfg.work_dir, cn).is_dir():
            click.secho(
                f" > Skipping registration of component {cn}: repo is not available",
                fg="yellow",
            )
            continue
        cdep = cfg.register_dependency_repo(cspec.url)
        component = Component(
            cn,
            work_dir=cfg.work_dir,
            dependency=cdep,
            sub_path=cspec.path,
            version=cspec.version,
        )
        cfg.register_component(component)
        create_component_symlinks(cfg, component)

    registered_components = cfg.get_components()
    pruned_aliases = {
        a: c for a, c in component_aliases.items() if c in registered_components.keys()
    }
    pruned = sorted(set(component_aliases.keys()) - set(pruned_aliases.keys()))
    if len(pruned) > 0:
        click.secho(
            f" > Dropping alias(es) {pruned} with missing component(s).", fg="yellow"
        )
    cfg.register_component_aliases(pruned_aliases)

    for alias, cn in pruned_aliases.items():
        if alias == cn:
            # Nothing to setup for identity alias
            continue

        c = registered_components[cn]
        aspec = cspecs[alias]

        adep = c.dependency
        if aspec.url != c.repo_url:
            adep = cfg.register_dependency_repo(aspec.url)
        c.register_alias(alias, aspec.version, adep, aspec.path)

        if not component_dir(cfg.work_dir, alias).is_dir():
            raise click.ClickException(f"Missing alias checkout for '{alias} as {cn}'")

        create_alias_symlinks(cfg, c, alias)


def fetch_packages(cfg: Config):
    """
    Download configuration packages used by the cluster.

    This function discovers packages which are used by parsing key `applications` in the
    hierarchy.
    """

    click.secho("Discovering config packages...", bold=True)
    cfg.inventory.ensure_dirs()
    pkgs = _discover_packages(cfg)
    pspecs = _read_packages(cfg, pkgs)

    deps: dict[str, list] = {}
    for p in pkgs:
        pspec = pspecs[p]
        pdep = cfg.register_dependency_repo(pspec.url)
        pkg = Package(
            p,
            dependency=pdep,
            target_dir=package_dependency_dir(cfg.work_dir, p),
            version=pspec.version,
            sub_path=pspec.path,
        )
        if pkg.checkout_is_dirty() and not cfg.force:
            raise click.ClickException(
                f"Package {p} has uncommitted changes. "
                + "Please specify `--force` to discard them"
            )
        deps.setdefault(pdep.url, []).append((p, pkg))
    do_parallel(fetch_package, cfg, deps.values())


def fetch_package(cfg: Config, dependencies: Iterable[tuple[str, Package]]):
    """
    Fetch all package dependencies of a MultiDependency object.
    """
    for p, pkg in dependencies:
        try:
            pkg.checkout()
        except RefError as e:
            raise ClickException(f"while fetching package {p}: {e}")
        cfg.register_package(p, pkg)
        create_package_symlink(cfg, p, pkg)


def register_packages(cfg: Config):
    """
    Discover configuration packages used by the cluster in the inventory and register
    them if they're checked out in `inventory/classes`.

    This function discovers packages which are used by parsing key `applications` in the
    hierarchy.
    """

    click.secho("Discovering config packages...", bold=True)
    cfg.inventory.ensure_dirs()
    pkgs = _discover_packages(cfg)
    pspecs = _read_packages(cfg, pkgs)
    for p in pkgs:
        pkg_dir = package_dependency_dir(cfg.work_dir, p)
        if not pkg_dir.is_dir():
            click.secho(
                f" > Skipping registration of package '{p}': repo is not available",
                fg="yellow",
            )
            continue
        pspec = pspecs[p]
        pdep = cfg.register_dependency_repo(pspec.url)
        pkg = Package(p, dependency=pdep, target_dir=pkg_dir, sub_path=pspec.path)
        cfg.register_package(p, pkg)
        create_package_symlink(cfg, p, pkg)


def verify_version_overrides(cluster_parameters, component_aliases: dict[str, str]):
    errors = []
    aliases = set(component_aliases.keys()) - set(component_aliases.values())
    for cname, cspec in cluster_parameters["components"].items():
        if cname in aliases:
            # We don't require an url in component alias version configs
            # but we do require the base component to have one
            if component_aliases[cname] not in cluster_parameters["components"]:
                errors.append(
                    f"component '{component_aliases[cname]}' (imported as {cname})"
                )
        elif "url" not in cspec:
            errors.append(f"component '{cname}'")

    for pname, pspec in cluster_parameters.get("packages", {}).items():
        if "url" not in pspec:
            errors.append(f"package '{pname}'")

    if len(errors) > 0:
        names = format_component_list(errors, format_func=lambda c: c)

        s = "s" if len(errors) > 1 else ""
        have = "have" if len(errors) > 1 else "has"

        raise click.ClickException(
            f"Version override{s} specified for {names} which {have} no URL"
        )
