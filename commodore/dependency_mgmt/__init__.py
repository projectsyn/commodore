from __future__ import annotations

import click

from commodore.config import Config
from commodore.component import Component, component_dir
from commodore.helpers import relsymlink

from .component_library import validate_component_library_name
from .discovery import _discover_components
from .tools import format_component_list
from .version_parsing import _read_components


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
        cnames = format_component_list(errors)
        s = "s" if len(errors) > 1 else ""
        have = "have" if len(errors) > 1 else "has"
        raise click.ClickException(
            f"Version override{s} specified for component{s} {cnames} which {have} no URL"
        )
