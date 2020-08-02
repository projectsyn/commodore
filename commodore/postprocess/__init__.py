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
    if not f["enabled"]:
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


def postprocess_components(config, kapitan_inventory, components: Dict[str, Component]):
    click.secho("Postprocessing...", bold=True)

    for cn, c in components.items():
        inventory = kapitan_inventory.get(cn)
        if not inventory:
            click.echo(f" > No target exists for component {cn}, skipping...")
            continue

        # inventory filters
        for f in _get_inventory_filters(inventory):
            if not _validate_filter(f):
                click.secho(
                    f"   > [WARN] Skipping filter '{f['filter']}' with invalid definition on path {f['path']}",
                    fg="yellow",
                )
                continue
            # TODO: check for missing filterpath for jsonnet filters
            if "enabled" not in f:
                f["enabled"] = True
            _run_filter(f, inventory, cn)

        # old filters
        filters_file = c.filters_file
        if filters_file.is_file():
            if config.debug:
                click.echo(f" > {cn}...")
            filters = yaml_load(filters_file)
            for f in filters["filters"]:
                # Add filterpath to filter dict
                f["filterpath"] = filters_file.parent
                # Add component name to filter dict
                f["component"] = cn

                # Add enabled flag if not present
                if "enabled" not in f:
                    f["enabled"] = True

                # Resolve any inventory references in filter definition
                try:
                    f = resolve_inventory_vars(inventory, f)
                except InventoryError as e:
                    raise click.ClickException(
                        f"Failed to resolve variables for non-inventory filter: {e}"
                    ) from e

                # filters without 'type' are always 'jsonnet'
                if "type" not in f:
                    click.secho(
                        "   > [WARN] component uses untyped non-inventory postprocess filter",
                        fg="yellow",
                    )
                    f["type"] = "jsonnet"
                # Filters which aren't explicitly disabled are always enabled
                if "enabled" in f and not f["enabled"]:
                    click.secho(
                        "   > Skipping disabled filter"
                        + f" {f['filter']} on path {f['path']}"
                    )
                    continue
                if f["type"] == "jsonnet":
                    run_jsonnet_filter(inventory, cn, filters_file.parent, f)
                elif f["type"] == "builtin":
                    run_builtin_filter(inventory, cn, f)
                else:
                    click.secho(
                        f"   > [WARN] unknown builtin filter {f['filter']}",
                        fg="yellow",
                    )
                _run_filter(f, inventory, cn)
