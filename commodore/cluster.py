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
    _cfg: Config
    _cluster_response: Dict
    _tenant_response: Dict

    def __init__(self, cfg: Config, cluster_response: Dict, tenant_response: Dict):
        self._cfg = cfg
        self._cluster = cluster_response
        self._tenant = tenant_response
        if (
            "tenant" not in self._cluster
            or self._cluster["tenant"] != self._tenant["id"]
        ):
            raise click.ClickException("Tenant ID mismatch")

    @property
    def id(self) -> str:
        return self._cluster["id"]

    @property
    def global_git_repo_url(self) -> str:
        field = "globalGitRepoURL"
        if field not in self._tenant:
            return f"{self._cfg.global_git_base}/commodore-defaults.git"
        return self._tenant[field]

    def _extract_field(self, field: str, default) -> str:
        """
        Extract `field` from the tenant and cluster data, preferring the value present in the cluster data over the
        value in the tenant data. If field is not present in both tenant and cluster data, return `default`.
        """
        return self._cluster.get(field, self._tenant.get(field, default))

    @property
    def global_git_repo_revision(self) -> str:
        return self._extract_field("globalGitRepoRevision", None)

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
    def config_git_repo_revision(self) -> str:
        return self._extract_field("gitRepoRevision", None)

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
        if "facts" not in self._cluster:
            return {}
        return self._cluster["facts"]


def load_cluster_from_api(cfg: Config, cluster_id: str) -> Cluster:
    cluster_response = lieutenant_query(
        cfg.api_url, cfg.api_token, "clusters", cluster_id
    )
    if "tenant" not in cluster_response:
        raise click.ClickException("cluster does not have a tenant reference")
    tenant_response = lieutenant_query(
        cfg.api_url, cfg.api_token, "tenants", cluster_response["tenant"]
    )
    return Cluster(cfg, cluster_response, tenant_response)


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


def render_params(cluster: Cluster):
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
            "cluster": {
                "name": cluster.id,
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


def params_file():
    return P("inventory", "classes", "params", "cluster.yml")


def update_params(cluster: Cluster):
    click.secho("Updating cluster parameters...", bold=True)
    file = params_file()
    os.makedirs(file.parent, exist_ok=True)
    yaml_dump(render_params(cluster), file)
