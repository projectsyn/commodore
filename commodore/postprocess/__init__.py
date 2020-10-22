from typing import Dict

import click

from commodore.component import Component
from commodore.helpers import yaml_load

from .jsonnet import run_jsonnet_filter, validate_jsonnet_filter
from .builtin_filters import run_builtin_filter, validate_builtin_filter
from .inventory import resolve_inventory_vars, InventoryError


def _get_inventory_filters(inventory):
    """
    Return list of filters defined in inventory.

    Inventory filters are expected to be defined as a list in
    `parameters.commodore.postprocess.filters`.
    """
    commodore = inventory["parameters"].get("commodore", {})
    return commodore.get("postprocess", {}).get("filters", [])


def _run_filter(f, inventory, component: str):
    if "enabled" in f and not f["enabled"]:
        click.secho(f"   > Skipping disabled filter {f['filter']} on path {f['path']}")
        return

    if f["type"] == "builtin":
        run_builtin_filter(inventory, component, f)
    elif f["type"] == "jsonnet":
        run_jsonnet_filter(inventory, component, f)
    else:
        click.secho(f"   > [WARN] unknown filter type {f['type']}", fg="yellow")


def _validate_filter(f):
    if "type" not in f:
        return False
    if f["type"] == "jsonnet":
        return validate_jsonnet_filter(f)
    if f["type"] == "builtin":
        return validate_builtin_filter(f)

    return False


def _get_external_filters(inventory, c: Component):
    filters_file = c.filters_file
    filters = []
    if filters_file.is_file():
        _filters = yaml_load(filters_file).get("filters", [])
        for f in _filters:
            # Resolve any inventory references in filter definition
            try:
                f = resolve_inventory_vars(inventory, f)
            except InventoryError as e:
                raise click.ClickException(
                    f"Failed to resolve variables for external filter: {e}"
                ) from e

            # external filters without 'type' are always 'jsonnet'
            if "type" not in f:
                click.secho(
                    "   > [WARN] component uses untyped external postprocessing filter",
                    fg="yellow",
                )
                f["type"] = "jsonnet"

            if f["type"] == "jsonnet":
                f["path"] = f["output_path"]
                del f["output_path"]
                f["filter"] = str(P("postprocess") / f["filter"])
            filters.append(f)
    return filters


def postprocess_components(config, kapitan_inventory, components: Dict[str, Component]):
    click.secho("Postprocessing...", bold=True)

    for cn, c in components.items():
        inventory = kapitan_inventory.get(cn)
        if not inventory:
            click.echo(f" > No target exists for component {cn}, skipping...")
            continue

        # inventory filters
        invfilters = _get_inventory_filters(inventory)

        # "old", external filters
        extfilters = _get_external_filters(inventory, c)

        filters = invfilters + extfilters

        if len(filters) > 0 and config.debug:
            click.echo(f" > {cn}...")

        for f in filters:
            if not _validate_filter(f):
                click.secho(
                    f"   > [WARN] Skipping filter '{f['filter']}' with invalid definition {f}",
                    fg="yellow",
                )
                continue

            if config.debug:
                click.secho(f"   > Executing filter '{f['type']}:{f['filter']}'")
            _run_filter(f, inventory, cn)
