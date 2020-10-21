import os

from pathlib import Path as P

from typing import Iterable, Tuple, Dict

import click

from .helpers import (
    lieutenant_query,
    yaml_dump,
    yaml_load,
)

from .config import Config


class Cluster:
    def __init__(self, cfg: Config, cluster_id: str):
        self._cfg = cfg
        self._cluster = lieutenant_query(
            cfg.api_url, cfg.api_token, "clusters", cluster_id
        )
        self._tenant = lieutenant_query(
            cfg.api_url, cfg.api_token, "tenants", self._cluster["tenant"]
        )
        if self._cluster["tenant"] != self._tenant["id"]:
            raise click.ClickException("Customer id mismatch")

    def id(self) -> str:
        return self._cluster["id"]

    @property
    def global_git_repo_url(self) -> str:
        field = "globalGitRepoURL"
        if field not in self._tenant:
            return f"{self._cfg.global_git_base}/commodore-defaults.git"
        return self._tenant[field]

    @property
    def config_repo_url(self) -> str:
        repo_url = self._tenant.get("gitRepo", {}).get("url", None)
        if repo_url is None:
            raise click.ClickException(
                " > API did not return a repository URL for tenant '%s'"
                % self._cluster["tenant"]
            )
        return repo_url

    @property
    def catalog_repo_url(self) -> str:
        repo_url = self._cluster.get("gitRepo", {}).get("url", None)
        if repo_url is None:
            raise click.ClickException(
                " > API did not return a repository URL for cluster '%s'"
                % self._cluster["id"]
            )
        return repo_url

    @property
    def tenant(self) -> str:
        return self._tenant["id"]

    @property
    def facts(self) -> Dict[str, str]:
        return self._cluster["facts"]


def read_cluster_and_tenant(target: str) -> Tuple[str, str]:
    """
    Reads the cluster and tenant ID from the current target.
    """
    file = params_file(target)
    if not file.is_file():
        raise click.ClickException(f"params file for target {target} does not exist")

    data = yaml_load(file)

    return (
        data["parameters"]["cluster"]["name"],
        data["parameters"]["cluster"]["tenant"],
    )


def render_target(target: str, components: Iterable[str]):
    classes = [f"params.{target}"]

    for component in components:
        defaults_file = P("inventory", "classes", "defaults") / f"{component}.yml"
        if defaults_file.is_file():
            classes.append(f"defaults.{component}")

    classes.append("global.commodore")

    return {
        "classes": classes,
    }


def target_file(target: str):
    return P("inventory", "targets") / f"{target}.yml"


def update_target(cfg: Config, target):
    click.secho("Updating Kapitan target...", bold=True)
    file = target_file(target)
    os.makedirs(file.parent, exist_ok=True)
    yaml_dump(render_target(target, cfg.get_components().keys()), file)


def render_params(cluster: Cluster, target: str):
    facts = cluster.facts
    for fact in ["distribution", "cloud"]:
        if fact not in facts or not facts[fact]:
            raise click.ClickException(f"Required fact '{fact}' not set")

    cloud = {
        "provider": facts["cloud"],
    }

    # TODO Remove after deprecation phase.
    if "region" in facts:
        cloud["region"] = facts["region"]

    data = {
        "parameters": {
            "target_name": target,
            "cluster": {
                "name": cluster.id(),
                "catalog_url": cluster.catalog_repo_url,
                "tenant": cluster.tenant,
                # TODO Remove dist after deprecation phase.
                "dist": facts["distribution"],
            },
            "facts": facts,
            # TODO Remove the cloud and customer parameters after deprecation phase.
            "cloud": cloud,
            "customer": {
                "name": cluster.tenant,
            },
        },
    }

    return data


def params_file(target: str):
    return P("inventory", "classes", "params") / f"{target}.yml"


def update_params(cluster: Cluster, target):
    click.secho("Updating cluster parameters...", bold=True)
    file = params_file(target)
    os.makedirs(file.parent, exist_ok=True)
    yaml_dump(render_params(cluster, target), file)
