from __future__ import annotations

import re
from collections.abc import Iterable

import click

from commodore.config import Config
from commodore.helpers import kapitan_inventory

from .tools import format_component_list

PACKAGE_PREFIX: str = "pkg."

RESERVED_PACKAGE_PATTERN = re.compile("^(components|defaults|global|params)$")
TENANT_PREFIX_PATTERN = re.compile("^t-.*$")


def _extract_component_aliases(
    cfg: Config, kapitan_applications: Iterable[str]
) -> tuple[set[str], dict[str, set[str]]]:
    """
    Extract components and all aliases from Kapitan applications array.

    This function doesn't validate the resulting data. Generally, callers will want to
    use `_discover_components()` to extract components and their aliases from the
    applications array.

    This function drops any packages included through the applications array.
    """
    components = set()
    all_component_aliases: dict[str, set[str]] = {}
    for component in kapitan_applications:
        if component.startswith(PACKAGE_PREFIX):
            continue
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

    return components, all_component_aliases


def _discover_components(cfg) -> tuple[list[str], dict[str, str]]:
    """
    Discover components used by the current cluster by extracting all entries from the
    reclass applications dictionary.

    The function also verifies the extracted entries, and raises an exception if any
    invalid aliases are found.
    """
    kapitan_applications = kapitan_inventory(cfg, key="applications")

    components, all_component_aliases = _extract_component_aliases(
        cfg, kapitan_applications.keys()
    )

    component_aliases: dict[str, str] = {}

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
                    clist = format_component_list(other_aliases)
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

            clist = format_component_list(cns)
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


def _discover_packages(cfg: Config) -> set[str]:
    """
    Discover configuration packages included through the applications array.

    All config package inclusions must be prefixed with `pkg.`. This function drops any
    component includes. To parse components from the applications array, use
    `_discover_components()`.
    """
    kapitan_applications = kapitan_inventory(
        cfg, key="applications", ignore_class_notfound=True
    )

    packages = set()

    for app in kapitan_applications:
        if not app.startswith(PACKAGE_PREFIX):
            continue

        pkgname = app.replace(PACKAGE_PREFIX, "", 1)

        if RESERVED_PACKAGE_PATTERN.match(pkgname):
            raise click.ClickException(
                f"Can't use reserved name '{pkgname}' as package name."
            )

        if TENANT_PREFIX_PATTERN.match(pkgname):
            raise click.ClickException(
                "Package names can't be prefixed with 't-'."
                + " This prefix is reserved for tenant configurations."
            )

        packages.add(pkgname)

    return packages
