from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import click
import semver

from cel_expr_python import cel  # type: ignore

from commodore.config import Config
from commodore.component import component_parameters_key


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
    path: Optional[str]
    minverspec: Optional[str]
    minversion: Optional[semver.Version]
    mandatory: bool
    requiredif: list[str]

    @classmethod
    def parse(
        cls, cname: str, depname: str, depspec: dict[str, str]
    ) -> ComponentDependency:
        if "url" not in depspec:
            raise ComponentDependencyParseError("url", "field 'url' missing")
        url = depspec["url"]
        minverspec = None
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
            depname,
            [cname],
            url,
            depspec.get("path"),
            minverspec,
            minversion,
            mandatory,
            requiredif,
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

        if self.path != other.path:
            raise ValueError(
                "Cannot merge ComponentDependency objects with same name and URL but different sub-paths: "
                + f"{self.path}, {other.path}"
            )

        if self.minversion and other.minversion:
            cur_self = self.minversion
            self.minversion = max(self.minversion, other.minversion)
            if cur_self != self.minversion:
                self.minverspec = other.minverspec
        elif other.minversion:
            self.minversion = other.minversion
            self.minverspec = other.minverspec

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

    def required_for_catalog(
        self, config: Config, cparams: dict[str, Any], facts: dict[str, Any]
    ) -> bool:
        if self.mandatory:
            return True

        required = False
        cel_env = cel.NewEnv(variables={"config": cel.Type.MAP, "facts": cel.Type.MAP})
        for expr in self.requiredif:
            if config.debug:
                click.echo(f"   > Evaluating CEL expression: {expr}")
            cel_expr = cel_env.compile(expr)
            res = cel_expr.eval(data={"config": cparams, "facts": facts})
            if res.type() == cel.Type.ERROR:
                raise ValueError(
                    f"Evaluation failed for `requiredif` CEL expression: {res.value()}"
                )
            if res.type() != cel.Type.BOOL:
                raise ValueError(
                    "Component dependency `requiredif` CEL expression must evaluate to a boolean"
                )
            resval = res.value()
            required = required or resval

        return required

    @property
    def component_entry(self) -> dict[str, str]:
        entry = {
            "url": self.url,
            "version": self.minverspec or "master",
        }
        if self.path:
            entry["path"] = self.path
        return entry


def collect_catalog_dependencies(
    config: Config, inventory: dict[str, Any]
) -> dict[str, ComponentDependency]:
    catalog_deps: dict[str, ComponentDependency] = {}
    for instance, cn in config.get_component_aliases().items():
        if config.debug:
            click.echo(f" > Collecting dependencies for component instance {instance}")
        params = inventory[instance]["parameters"]
        deps = map(
            lambda d: ComponentDependency.parse(instance, *d),
            params.get("commodore", {}).get("dependencies", {}).items(),
        )

        for dep in deps:
            if not dep.required_for_catalog(
                config, params[component_parameters_key(cn)], params["facts"]
            ):
                if config.debug:
                    click.echo(f"   > Dependency {dep.name} not required for catalog")
                continue

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
