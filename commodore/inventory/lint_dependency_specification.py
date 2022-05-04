from __future__ import annotations

from pathlib import Path
from typing import Any

import click
from commodore.dependency_mgmt.version_parsing import DepType


def lint_dependency_specification(
    deptype: DepType, file: Path, filecontents: dict[str, Any]
) -> int:
    errcount = 0
    components = filecontents.get("parameters", {}).get(deptype.value, {})
    deptype_str = deptype.name.capitalize()
    for d, dspec in components.items():
        if "version" not in dspec:
            click.secho(
                f"> {deptype_str} specification for {d} "
                + f"is missing key 'version' in {file}",
                fg="red",
            )
            errcount += 1

        unk_keys = set(dspec.keys()) - {"url", "version"}
        if len(unk_keys) > 0:
            click.secho(
                f"> {deptype_str} specification for {d} "
                + f"contains unknown key(s) '{unk_keys}' in {file}",
                fg="red",
            )
            errcount += 1

        durl = dspec.get("url", "")
        if not isinstance(durl, str):
            click.secho(
                f"> {deptype_str} {d} url is of type {type(durl).__name__}"
                + f" (expected string) in {file}",
                fg="red",
            )
            errcount += 1

        dversion = dspec.get("version", "")
        if not isinstance(dversion, str):
            click.secho(
                f"> {deptype_str} {d} version is of type {type(dversion).__name__},"
                + f" (expected string) in {file}",
                fg="red",
            )
            errcount += 1

    return errcount


def lint_components(file: Path, filecontents: dict[str, Any]) -> int:
    return lint_dependency_specification(DepType.COMPONENT, file, filecontents)


def lint_packages(file: Path, filecontents: dict[str, Any]) -> int:
    return lint_dependency_specification(DepType.PACKAGE, file, filecontents)
