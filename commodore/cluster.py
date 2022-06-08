from __future__ import annotations

import os

from typing import Any, Optional, Union

import click

from .helpers import (
    lieutenant_query,
    yaml_dump,
    yaml_load,
)

from .component import component_parameters_key, Component
from .config import Config
from .inventory import Inventory


class Cluster:
    _cluster_response: dict
    _tenant_response: dict

    def __init__(self, cluster_response: dict, tenant_response: dict):
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
    def display_name(self) -> str:
        return self._cluster["displayName"]

    @property
    def global_git_repo_url(self) -> str:
        field = "globalGitRepoURL"
        if field not in self._tenant:
            raise click.ClickException(
                f"URL of the global git repository is missing on tenant '{self.tenant_id}'"
            )
        return self._tenant[field]

    def _extract_field(self, field: str, default) -> str:
        """
        Extract `field` from the tenant and cluster data, preferring the value present in the
        cluster data over the value in the tenant data. If field is not present in both tenant and
        cluster data, return `default`.
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
                f" > API did not return a repository URL for tenant '{self._cluster['tenant']}'"
            )
        return repo_url

    @property
    def config_git_repo_revision(self) -> str:
        return self._extract_field("tenantGitRepoRevision", None)

    @property
    def catalog_repo_url(self) -> str:
        repo_url = self._cluster.get("gitRepo", {}).get("url", None)
        if repo_url is None:
            raise click.ClickException(
                f" > API did not return a repository URL for cluster '{self._cluster['id']}'"
            )
        return repo_url

    @property
    def tenant_id(self) -> str:
        return self._tenant["id"]

    @property
    def tenant_display_name(self) -> str:
        return self._tenant["displayName"]

    @property
    def facts(self) -> dict[str, str]:
        return self._cluster.get("facts", {})

    @property
    def dynamic_facts(self) -> dict[str, Any]:
        return self._cluster.get("dynamicFacts", {})


def load_cluster_from_api(cfg: Config, cluster_id: str) -> Cluster:
    cluster_response = lieutenant_query(
        cfg.api_url, cfg.api_token, "clusters", cluster_id
    )
    if "tenant" not in cluster_response:
        raise click.ClickException("cluster does not have a tenant reference")
    tenant_response = lieutenant_query(
        cfg.api_url, cfg.api_token, "tenants", cluster_response["tenant"]
    )
    return Cluster(cluster_response, tenant_response)


def read_cluster_and_tenant(inv: Inventory) -> tuple[str, str]:
    """
    Reads the cluster and tenant ID from the current target.
    """
    file = inv.params_file
    if not file.is_file():
        raise click.ClickException(f"params file for {file.stem} does not exist")

    data = yaml_load(file)

    return (
        data["parameters"][inv.bootstrap_target]["name"],
        data["parameters"][inv.bootstrap_target]["tenant"],
    )


def render_target(
    inv: Inventory,
    target: str,
    components: dict[str, Component],
    # pylint: disable=unsubscriptable-object
    component: Optional[str] = None,
):
    if not component:
        component = target
    bootstrap = target == inv.bootstrap_target
    if not bootstrap and component not in components:
        raise click.ClickException(f"Target {target} is not a component")

    classes = [f"params.{inv.bootstrap_target}"]
    parameters: dict[str, Union[dict, str]] = {
        "_instance": target,
    }
    if not bootstrap:
        parameters["_base_directory"] = str(components[component].target_directory)

    for c in components:
        if inv.defaults_file(c).is_file():
            classes.append(f"defaults.{c}")
        else:
            click.secho(f" > Default file for class {c} missing", fg="yellow")

    classes.append("global.commodore")

    if not bootstrap:
        if not inv.component_file(component).is_file():
            raise click.ClickException(
                f"Target rendering failed for {target}: component class is missing"
            )
        classes.append(f"components.{component}")
        parameters["kapitan"] = {
            "vars": {
                "target": target,
            },
        }

        # When component != target we're rendering a target for an aliased
        # component. This needs some extra work.
        if component != target:
            ckey = component_parameters_key(component)
            tkey = component_parameters_key(target)
            parameters[tkey] = {}
            parameters[ckey] = f"${{{tkey}}}"

    return {
        "classes": classes,
        "parameters": parameters,
    }


# pylint: disable=unsubscriptable-object
def update_target(cfg: Config, target: str, component: Optional[str] = None):
    click.secho(f"Updating Kapitan target for {target}...", bold=True)
    file = cfg.inventory.target_file(target)
    os.makedirs(file.parent, exist_ok=True)
    targetdata = render_target(
        cfg.inventory, target, cfg.get_components(), component=component
    )
    yaml_dump(targetdata, file)


def render_params(inv: Inventory, cluster: Cluster):
    facts = cluster.facts
    dynfacts = cluster.dynamic_facts
    for fact in ["distribution", "cloud"]:
        if fact not in facts or not facts[fact]:
            raise click.ClickException(f"Required fact '{fact}' not set")

    data = {
        "parameters": {
            inv.bootstrap_target: {
                "name": cluster.id,
                "display_name": cluster.display_name,
                "catalog_url": cluster.catalog_repo_url,
                "tenant": cluster.tenant_id,
                "tenant_display_name": cluster.tenant_display_name,
            },
            "facts": facts,
            "dynamic_facts": dynfacts,
        },
    }

    return data


def update_params(inv: Inventory, cluster: Cluster):
    click.secho("Updating cluster parameters...", bold=True)
    file = inv.params_file
    os.makedirs(file.parent, exist_ok=True)
    yaml_dump(render_params(inv, cluster), file)
