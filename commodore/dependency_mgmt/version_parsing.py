from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Optional

from enum import Enum

import click

from commodore.config import Config
from commodore.helpers import kapitan_inventory


class DepType(Enum):
    COMPONENT = "components"
    PACKAGE = "packages"


class DependencyParseError(ValueError):
    field: str

    def __init__(self, field: str):
        super().__init__("Error parsing dependency specification")
        self.field = field


@dataclass
class DependencySpec:
    """Class for parsed Dependency specification"""

    url: str
    version: str
    path: str

    @classmethod
    def parse(
        cls,
        info: dict[str, str],
        base_config: Optional[DependencySpec] = None,
    ) -> DependencySpec:
        if "url" not in info and not base_config:
            raise DependencyParseError("url")

        if "version" not in info and not base_config:
            raise DependencyParseError("version")

        path = info.get("path", "")
        if path.startswith("/"):
            path = path[1:]

        if base_config:
            url = info.get("url", base_config.url)
            version = info.get("version", base_config.version)
            if not path:
                path = base_config.path
        else:
            url = info["url"]
            version = info["version"]

        return DependencySpec(url, version, path)


def _read_versions(
    cfg: Config,
    dependency_type: DepType,
    dependency_names: Iterable[str],
    require_key: bool = True,
    ignore_class_notfound: bool = False,
    aliases: dict[str, str] = {},
    fallback: dict[str, DependencySpec] = {},
) -> dict[str, DependencySpec]:
    deps_key = dependency_type.value
    deptype_str = dependency_type.name.lower()
    deptype_cap = deptype_str.capitalize()
    dependencies = {}

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

    if aliases:
        all_dep_keys = set(aliases.keys())
    else:
        all_dep_keys = deps.keys()
    for depname in dependency_names:
        if depname not in all_dep_keys:
            raise click.ClickException(
                f"Unknown {deptype_str} '{depname}'."
                + f" Please add it to 'parameters.{deps_key}'"
            )

        try:
            basename_for_dep = aliases.get(depname, depname)
            dep = DependencySpec.parse(
                deps.get(depname, {}),
                base_config=fallback.get(basename_for_dep),
            )
        except DependencyParseError as e:
            raise click.ClickException(
                f"{deptype_cap} '{depname}' is missing field '{e.field}'"
            )

        if cfg.debug:
            click.echo(f" > URL for {depname}: {dep.url}")
            click.echo(f" > Version for {depname}: {dep.version}")
            click.echo(f" > Subpath for {depname}: {dep.path}")

        dependencies[depname] = dep

    return dependencies


def _read_components(
    cfg: Config, component_aliases: dict[str, str]
) -> dict[str, DependencySpec]:
    component_names = set(component_aliases.values())
    alias_names = set(component_aliases.keys()) - component_names

    component_versions = _read_versions(cfg, DepType.COMPONENT, component_names)
    alias_versions = _read_versions(
        cfg,
        DepType.COMPONENT,
        alias_names,
        aliases=component_aliases,
        fallback=component_versions,
    )

    for alias, aspec in alias_versions.items():
        if alias in component_versions:
            raise ValueError("alias name already in component_versions?")
        component_versions[alias] = aspec

    return component_versions


def _read_packages(
    cfg: Config, package_names: Iterable[str]
) -> dict[str, DependencySpec]:
    return _read_versions(
        cfg,
        DepType.PACKAGE,
        package_names,
        require_key=False,
        ignore_class_notfound=True,
    )
