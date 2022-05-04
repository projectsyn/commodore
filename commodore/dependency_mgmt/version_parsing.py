from __future__ import annotations

from typing import Optional

import click

from commodore.config import Config
from commodore.helpers import kapitan_inventory


def _read_components(
    cfg: Config, component_names
) -> tuple[dict[str, str], dict[str, Optional[str]]]:
    component_urls = {}
    component_versions = {}

    inv = kapitan_inventory(cfg)
    cluster_inventory = inv[cfg.inventory.bootstrap_target]
    components = cluster_inventory["parameters"].get("components", None)
    if not components:
        raise click.ClickException("Component list ('parameters.components') missing")

    for component_name in component_names:
        if component_name not in components:
            raise click.ClickException(
                f"Unknown component '{component_name}'. Please add it to 'parameters.components'"
            )

        info = components[component_name]

        if "url" not in info:
            raise click.ClickException(
                f"No url for component '{component_name}' configured"
            )

        component_urls[component_name] = info["url"]
        if cfg.debug:
            click.echo(f" > URL for {component_name}: {component_urls[component_name]}")
        if "version" in info:
            component_versions[component_name] = info["version"]
        else:
            raise click.ClickException(
                f"Component '{component_name}' doesn't have a version specified."
            )
        if cfg.debug:
            click.echo(
                f" > Version for {component_name}: {component_versions[component_name]}"
            )

    return component_urls, component_versions
