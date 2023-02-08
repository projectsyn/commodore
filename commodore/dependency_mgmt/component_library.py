from __future__ import annotations

from typing import Any
from pathlib import Path

import click

from commodore.component import Component
from commodore.config import Config
from commodore.helpers import relsymlink

from .tools import format_component_list


def validate_component_library_name(cname: str, lib: Path) -> Path:
    if not lib.stem.startswith(cname):
        raise click.ClickException(
            f"Component '{cname}' uses invalid component library name '{lib.name}'. "
            + "Consider using a library alias."
        )

    return lib


def _check_library_alias_prefixes(
    libalias: str,
    cn: str,
    component_prefixes: set[str],
    additional_prefix: str,
):
    prefixes = component_prefixes - {cn}
    if additional_prefix:
        prefixes = prefixes - {additional_prefix}
    for p in prefixes:
        if libalias.startswith(p):
            raise click.ClickException(
                f"Invalid alias prefix '{p}' "
                + f"for template library alias of component '{cn}'"
            )


def _read_additional_prefix(
    cn: str,
    cmeta: dict[str, Any],
    components: dict[str, Component],
    cluster_params: dict[str, Any],
) -> str:
    """Extract additional allowed library prefixes from component metadata.

    If a component matching the additional prefix is present in the cluster
    config, we verify that additional prefix is ok by checking that that
    component is deprecated and has nominated us as their replacement.
    """
    additional_cname = cmeta.get("replaces", "")
    if additional_cname and additional_cname in components:
        ometa = cluster_params[components[additional_cname].parameters_key].get(
            "_metadata", {}
        )
        odeprecated = ometa.get("deprecated", False)
        oreplaced_by = ometa.get("replaced_by", "")
        if not odeprecated:
            click.secho(
                f" > Ignoring additional library prefix '{additional_cname}' "
                + f"requested by '{cn}'. Component '{additional_cname}' is "
                + "also deployed on the cluster and isn't deprecated.",
                fg="red",
            )
            additional_cname = ""
        elif oreplaced_by != cn:
            click.secho(
                f" > Ignoring additional library prefix '{additional_cname}' "
                + f"requested by '{cn}'. Component '{additional_cname}' is "
                + f"also deployed on the cluster and hasn't nominated '{cn}' "
                + "as its replacement.",
                fg="red",
            )
            additional_cname = ""
        else:
            click.secho(
                f" > Allowing additional library prefix '{additional_cname}' "
                + f"for component '{cn}'. Component '{additional_cname}' "
                + f"is marked as deprecated and has nominated component '{cn}' "
                + "as its replacement.",
                fg="yellow",
            )

    return additional_cname


def _check_library_alias_collisions(cfg: Config, cluster_params: dict[str, Any]):
    # map of library alias to set(originating components)
    collisions: dict[str, set[str]] = {}

    components = cfg.get_components()
    component_prefixes = set(cluster_params["components"].keys())

    for cn, component in components.items():
        cmeta = cluster_params[component.parameters_key].get("_metadata", {})
        aliases = cmeta.get("library_aliases", {})
        # If component replaces another component, and wants to use the old component's
        # library prefix, it should set `_metadata.replaces` to the old component name.
        # _read_additional_prefix() also sanity-checks the specified additional prefix,
        # see docstring for details.
        additional_prefix = _read_additional_prefix(
            cn, cmeta, components, cluster_params
        )

        for libalias in aliases.keys():
            _check_library_alias_prefixes(
                libalias, cn, component_prefixes, additional_prefix
            )
            collisions.setdefault(libalias, set()).add(cn)

    for libalias, cnames in collisions.items():
        if len(cnames) > 1:
            clist = format_component_list(cnames)
            _all = "all" if len(cnames) > 2 else "both"
            raise click.ClickException(
                f"Components {clist} {_all} define component library alias '{libalias}'"
            )


def create_component_library_aliases(cfg: Config, cluster_params: dict[str, Any]):
    click.secho("Installing component library aliases", bold=True)
    _check_library_alias_collisions(cfg, cluster_params)

    components = cfg.get_components()

    for cn, component in components.items():
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
