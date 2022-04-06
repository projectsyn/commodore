from pathlib import Path
from typing import Any, Dict

import click

from commodore.config import Config

from .lint import run_linter


def _lint_component_versions(file: Path, filecontents: Dict[str, Any]) -> int:
    errcount = 0
    components = filecontents.get("parameters", {}).get("components", {})
    for cn, cspec in components.items():
        if "version" not in cspec:
            click.secho(
                f"> Component specification for {cn} is missing explict version in {file}",
                fg="red",
            )
            errcount += 1
    return errcount


def lint_components(cfg: Config, path: Path) -> int:
    return run_linter(cfg, path, _lint_component_versions)
