from __future__ import annotations

import click

from commodore.config import Config
from commodore.component import Component, component_dir
from commodore.helpers import relsymlink
from commodore.package import Package, package_dependency_dir

from .component_library import validate_component_library_name
from .discovery import _discover_components, _discover_packages
from .tools import format_component_list
from .version_parsing import _read_components, _read_packages


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
    cspecs = _read_components(cfg, component_names)
    click.secho("Fetching components...", bold=True)
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
        c.checkout()
        cfg.register_component(c)
        create_component_symlinks(cfg, c)


def register_components(cfg: Config):
    """
    Discover components in the inventory, and register them if the
    corresponding directory in `dependencies/` exists.

    Create component symlinks for discovered components which exist.
    """
    click.secho("Discovering included components...", bold=True)
    try:
        components, component_aliases = _discover_components(cfg)
        cspecs = _read_components(cfg, components)
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
        pkg.checkout()
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


def verify_version_overrides(cluster_parameters):
    errors = []
    for cname, cspec in cluster_parameters["components"].items():
        if "url" not in cspec:
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
