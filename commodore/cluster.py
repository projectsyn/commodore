import os

from pathlib import Path as P

from typing import Iterable, Tuple

import click

from .helpers import (
    lieutenant_query,
    yaml_dump,
    yaml_load,
)

from .config import Config


def fetch_cluster(cfg, clusterid):
    cluster = lieutenant_query(cfg.api_url, cfg.api_token, "clusters", clusterid)
    # TODO: move Commodore global defaults repo name into Lieutenant
    # API/cluster facts
    cluster["base_config"] = "commodore-defaults"
    return cluster


def read_cluster_and_tenant() -> Tuple[str, str]:
    """
    Reads the cluster and tenant ID from the current target.
    """
    file = params_file()
    if not file.is_file():
        raise click.ClickException(f"params file for {file.stem} does not exist")

    data = yaml_load(file)

    return (
        data["parameters"]["cluster"]["name"],
        data["parameters"]["cluster"]["tenant"],
    )


def render_target(target: str, components: Iterable[str], bootstrap=False):
    if not bootstrap and target not in components:
        raise click.ClickException(f"Target {target} is not a component")

    classes = ["params.cluster"]
    parameters = {}

    for component in components:
        defaults_file = P("inventory", "classes", "defaults") / f"{component}.yml"
        if defaults_file.is_file():
            classes.append(f"defaults.{component}")

    classes.append("global.commodore")

    if not bootstrap:
        component_file = P("inventory", "classes", "components") / f"{target}.yml"
        if not component_file.is_file():
            raise click.ClickException(
                f"Target rendering failed for {target}: component class is missing"
            )
        classes.append(f"components.{target}")
        parameters = {
            "kapitan": {
                "vars": {
                    "target": target,
                }
            }
        }

    return {
        "classes": classes,
        "parameters": parameters,
    }


def target_file(target: str):
    return P("inventory", "targets") / f"{target}.yml"


def update_target(cfg: Config, target: str, bootstrap=False):
    click.secho(f"Updating Kapitan target for {target}...", bold=True)
    file = target_file(target)
    os.makedirs(file.parent, exist_ok=True)
    targetdata = render_target(target, cfg.get_components().keys(), bootstrap=bootstrap)
    yaml_dump(targetdata, file)


def render_params(cluster):
    facts = cluster["facts"]
    for fact in ["distribution", "cloud"]:
        if fact not in facts or not facts[fact]:
            raise click.ClickException(f"Required fact '{fact}' not set")

    data = {
        "parameters": {
            "cluster": {
                "name": cluster["id"],
                "catalog_url": cluster["gitRepo"]["url"],
                "tenant": cluster["tenant"],
                # TODO Remove dist after deprecation phase.
                "dist": facts["distribution"],
            },
            "facts": facts,
            # TODO Remove the cloud and customer parameters after deprecation phase.
            "cloud": {
                "provider": facts["cloud"],
            },
            "customer": {
                "name": cluster["tenant"],
            },
        },
    }

    # TODO Remove after deprecation phase.
    if "region" in facts:
        data["parameters"]["cloud"]["region"] = facts["region"]

    return data


def params_file():
    return P("inventory", "classes", "params", "cluster.yml")


def update_params(cluster):
    click.secho("Updating cluster parameters...", bold=True)
    file = params_file()
    os.makedirs(file.parent, exist_ok=True)
    yaml_dump(render_params(cluster), file)
