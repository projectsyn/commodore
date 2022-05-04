from __future__ import annotations

from typing import Any
from pathlib import Path

import click

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


def _check_library_alias_prefixes(libalias: str, cn: str, component_prefixes: set[str]):
    for p in component_prefixes - {cn}:
        if libalias.startswith(p):
            raise click.ClickException(
                f"Invalid alias prefix '{p}' "
                + f"for template library alias of component '{cn}'"
            )


def _check_library_alias_collisions(cfg: Config, cluster_params: dict[str, Any]):
    # map of library alias to set(originating components)
    collisions: dict[str, set[str]] = {}

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
            clist = format_component_list(cnames)
            _all = "all" if len(cnames) > 2 else "both"
            raise click.ClickException(
                f"Components {clist} {_all} define component library alias '{libalias}'"
            )


def create_component_library_aliases(cfg: Config, cluster_params: dict[str, Any]):
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
