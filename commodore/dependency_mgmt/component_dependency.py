from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import click
import semver

from commodore.config import Config


class ComponentDependencyParseError(ValueError):
    field: str
    reason: Optional[str]

    def __init__(self, field: str, reason: Optional[str] = ""):
        msg = "Error parsing dependency specification"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)
        self.field = field
        self.reason = reason


@dataclass
class ComponentDependency:
    """Class for parsed component dependency specification"""

    name: str
    instances: list[str]
    url: str
    minversion: Optional[semver.Version]
    mandatory: bool
    requiredif: list[str]

    @classmethod
    def parse(
        cls, cname: str, depname: str, depspec: dict[str, str]
    ) -> ComponentDependency:
        if "url" not in depspec:
            raise ComponentDependencyParseError("url")
        url = depspec["url"]
        if "minversion" in depspec:
            minverspec = depspec["minversion"]
            try:
                if minverspec.startswith("v"):
                    minversion = semver.Version.parse(minverspec[1:])
                else:
                    minversion = semver.Version.parse(minverspec)
            except ValueError as e:
                raise ComponentDependencyParseError("minversion", str(e))
        else:
            minversion = None

        # NOTE(sg): if requiredif isn't set, the dependency is mandatory
        mandatory = "requiredif" not in depspec
        requiredif = []
        if not mandatory:
            requiredif = [depspec["requiredif"]]

        return ComponentDependency(
            depname, [cname], url, minversion, mandatory, requiredif
        )

    def update(self, other: ComponentDependency):
        if self.name != other.name:
            raise ValueError(
                f"Cannot merge ComponentDependency objects with different names: {self.name}, {other.name}"
            )
        if self.url != other.url:
            raise ValueError(
                f"Cannot merge ComponentDependency objects with same name but different URLs: {self.url}, {other.url}"
            )

        if self.minversion and other.minversion:
            self.minversion = max(self.minversion, other.minversion)
        elif other.minversion:
            self.minversion = other.minversion

        self.mandatory = self.mandatory or other.mandatory
        self.requiredif.extend(other.requiredif)
        self.instances.extend(other.instances)

    def _error_helper(self) -> tuple[str, str]:
        if len(self.instances) == 1:
            instances = "instance"
            require = "requires"
        else:
            instances = "instances"
            require = "require"

        return (instances, require)

    def missing_dependency_error(self) -> str:
        instances, require = self._error_helper()
        instances_list = ", ".join(map(lambda i: f"'{i}'", self.instances))
        return (
            f"Component {instances} {instances_list} {require} dependency "
            + f"'{self.name}' which isn't present in catalog"
        )

    def not_minversion_error(self, cv: str) -> str:
        instances, require = self._error_helper()
        instances_list = ", ".join(map(lambda i: f"'{i}'", self.instances))
        return (
            f"Component {instances} {instances_list} {require} dependency '{self.name}' "
            + f"in a version '>= {self.minverspec}': catalog has '{cv}'"
        )


def collect_catalog_dependencies(
    config: Config, inventory: dict[str, Any]
) -> dict[str, ComponentDependency]:
    catalog_deps: dict[str, ComponentDependency] = {}
    for instance, cn in config.get_component_aliases().items():
        params = inventory[instance]["parameters"]
        deps = map(
            lambda d: ComponentDependency.parse(instance, *d),
            params.get("commodore", {}).get("dependencies", {}).items(),
        )

        for dep in deps:
            if dep.name in catalog_deps:
                catalog_deps[dep.name].update(dep)
            else:
                catalog_deps[dep.name] = dep

    return catalog_deps


def validate_catalog_dependencies(config: Config, inventory: dict[str, Any]):
    click.secho("Validating component dependencies...", bold=True)
    catalog_deps = collect_catalog_dependencies(config, inventory)
    deperrs = []
    for dn, dep in catalog_deps.items():
        if config.verbose:
            click.echo(f" > Validating dependency {dn}")
        d = config.get_components().get(dn)
        if not d:
            deperrs.append(dep.missing_dependency_error())
            continue

        if dep.minversion:
            try:
                if not d.version:
                    raise ValueError("component instance {dn} missing version")

                if d.version.startswith("v"):
                    dv = semver.Version.parse(d.version[1:])
                else:
                    dv = semver.Version.parse(d.version)
            except ValueError:
                if config.verbose:
                    click.echo(
                        f"   > Dependency '{dn}' present in catalog with version '{d.version}' "
                        + f"which doesn't parse as SemVer: assuming '{d.version} >= {dep.minversion}'"
                    )
                continue
            if dep.minversion > dv:
                deperrs.append(dep.not_minversion_error(d.version))

    if len(deperrs) > 0:
        deperrs_str = "\n * ".join(deperrs)
        raise click.ClickException(
            f"catalog dependency validation failed:\n * {deperrs_str}"
        )
