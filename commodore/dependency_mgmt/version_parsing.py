from __future__ import annotations

from collections.abc import Iterable

from enum import Enum
from typing import Optional

import click

from commodore.config import Config
from commodore.helpers import kapitan_inventory


class DepType(Enum):
    COMPONENT = "components"
    PACKAGE = "packages"


def _read_versions(
    cfg: Config,
    dependency_type: DepType,
    dependency_names: Iterable[str],
    require_key: bool = True,
    ignore_class_notfound: bool = False,
) -> tuple[dict[str, str], dict[str, Optional[str]]]:
    dep_urls = {}
    dep_versions = {}
    deps_key = dependency_type.value
    deptype_str = dependency_type.name.lower()
    deptype_cap = deptype_str.capitalize()

    inv = kapitan_inventory(cfg, ignore_class_notfound=ignore_class_notfound)
    cluster_inventory = inv[cfg.inventory.bootstrap_target]
    deps = cluster_inventory["parameters"].get(deps_key, None)
    if not deps:
        if require_key:
            raise click.ClickException(
                f"{deptype_cap} list ('parameters.{deps_key}') missing"
            )
        # If we don't require the key for the requested dependency type to be present,
        # just set deps to the empty dict.
        deps = {}

    for depname in dependency_names:
        if depname not in deps:
            raise click.ClickException(
                f"Unknown {deptype_str} '{depname}'."
                + f" Please add it to 'parameters.{deps_key}'"
            )

        info = deps[depname]

        if "url" not in info:
            raise click.ClickException(
                f"No url for {deptype_str} '{depname}' configured"
            )

        dep_urls[depname] = info["url"]
        if cfg.debug:
            click.echo(f" > URL for {depname}: {dep_urls[depname]}")
        if "version" in info:
            dep_versions[depname] = info["version"]
        else:
            raise click.ClickException(
                f"{deptype_cap} '{depname}' doesn't have a version specified."
            )
        if cfg.debug:
            click.echo(f" > Version for {depname}: {dep_versions[depname]}")

    return dep_urls, dep_versions


def _read_components(
    cfg: Config, component_names: Iterable[str]
) -> tuple[dict[str, str], dict[str, Optional[str]]]:
    return _read_versions(cfg, DepType.COMPONENT, component_names)


def _read_packages(
    cfg: Config, package_names: Iterable[str]
) -> tuple[dict[str, str], dict[str, Optional[str]]]:
    return _read_versions(
        cfg,
        DepType.PACKAGE,
        package_names,
        require_key=False,
        ignore_class_notfound=True,
    )
