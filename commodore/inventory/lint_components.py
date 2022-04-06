from pathlib import Path
from typing import Any, Dict

import click


def lint_component_versions(file: Path, filecontents: Dict[str, Any]) -> int:
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
