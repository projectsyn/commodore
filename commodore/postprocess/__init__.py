from pathlib import Path as P

import click

from commodore.helpers import yaml_load

from .jsonnet import run_jsonnet_filter
from .builtin_filters import run_builtin_filter
from .inventory import resolve_inventory_vars, InventoryError


def postprocess_components(config, kapitan_inventory, components):
    click.secho("Postprocessing...", bold=True)
    for cn, c in components.items():
        inventory = kapitan_inventory.get(cn)
        if not inventory:
            click.echo(f" > No target exists for component {cn}, skipping...")
            continue

        repodir = P(c.repo.working_tree_dir)
        filterdir = repodir / "postprocess"
        if filterdir.is_dir():
            if config.debug:
                click.echo(f" > {cn}...")
            filters = yaml_load(filterdir / "filters.yml")
            for f in filters["filters"]:
                # Resolve any inventory references in filter definition
                try:
                    f = resolve_inventory_vars(inventory, f)
                except InventoryError as e:
                    raise click.ClickException(
                        f"Failed to resolve variables for old-style filter: {e}"
                    ) from e

                # filters without 'type' are always 'jsonnet'
                if "type" not in f:
                    click.secho(
                        "   > [WARN] component uses old-style postprocess filters",
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
                    run_jsonnet_filter(inventory, cn, filterdir, f)
                elif f["type"] == "builtin":
                    run_builtin_filter(inventory, cn, f)
                else:
                    click.secho(
                        f"   > [WARN] unknown builtin filter {f['filter']}",
                        fg="yellow",
                    )
