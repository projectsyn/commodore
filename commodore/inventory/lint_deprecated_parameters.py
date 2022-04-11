from __future__ import annotations

from pathlib import Path
from typing import Any

import click

DEPRECATED_PARAMS = [
    "${customer:name}",
    "${cloud:provider}",
    "${cloud:region}",
    "${cluster:dist}",
]


def _lint_data(file: Path, prefix: str, data: Any) -> int:
    if isinstance(data, dict):
        return _lint_dict(file, prefix, data)
    if isinstance(data, list):
        return _lint_list(file, prefix, data)
    if isinstance(data, str):
        return _lint_string(file, prefix, data)

    # Only dicts, lists, or strings can contain parameter references
    return 0


def _lint_string(file: Path, prefix: str, data: str) -> int:
    errcount = 0

    for p in DEPRECATED_PARAMS:
        if p in data:
            click.secho(
                f"> Field '{prefix}' in file '{file}' contains deprecated parameter '{p}'",
                fg="red",
            )
            errcount += 1

    return errcount


def _lint_list(file: Path, prefix: str, data: list) -> int:
    errcount = 0
    for i, v in enumerate(data):
        errcount += _lint_data(file, prefix + f"[{i}]", v)

    return errcount


def _lint_dict(file: Path, prefix: str, data: dict[str, Any]) -> int:
    errcount = 0
    if prefix != "":
        prefix = f"{prefix}."
    for k, v in data.items():
        errcount += _lint_data(file, prefix + k, v)

    return errcount


def lint_deprecated_parameters(file: Path, filecontents: dict[str, Any]) -> int:
    prefix = ""
    return _lint_dict(file, prefix, filecontents)
