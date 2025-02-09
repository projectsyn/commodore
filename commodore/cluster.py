from __future__ import annotations

import json
import os
import textwrap

from datetime import datetime
from typing import Any, Optional, Union

import click

from . import __kustomize_wrapper__, __git_version__, __version__
from .helpers import (
    lieutenant_post,
    lieutenant_query,
    yaml_dump,
    yaml_load,
)

from .component import component_parameters_key, Component
from .config import Config
from .inventory import Inventory
from .login import login


class Cluster:
    _cluster_response: dict
    _tenant_response: dict
    _fallback_dynamic_facts: dict[str, Any]

    def __init__(
        self,
        cluster_response: dict,
        tenant_response: dict,
        fallback_dynamic_facts: dict[str, Any] = {},
    ):
        self._cluster = cluster_response
        self._tenant = tenant_response
        self._fallback_dynamic_facts = fallback_dynamic_facts

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
        if "dynamicFacts" in self._cluster and self._fallback_dynamic_facts:
            empty = "" if self._cluster["dynamicFacts"] else "empty "
            click.secho(
                f" > Cluster API response contains {empty}dynamic facts, ignoring "
                + " dynamic facts provided on the command line."
            )

        return self._cluster.get("dynamicFacts", self._fallback_dynamic_facts)


def load_cluster_from_api(cfg: Config, cluster_id: str) -> Cluster:
    cluster_response = lieutenant_query(
        cfg.api_url, cfg.api_token, "clusters", cluster_id, timeout=cfg.request_timeout
    )
    if "tenant" not in cluster_response:
        raise click.ClickException("cluster does not have a tenant reference")
    tenant_response = lieutenant_query(
        cfg.api_url,
        cfg.api_token,
        "tenants",
        cluster_response["tenant"],
        timeout=cfg.request_timeout,
    )
    return Cluster(cluster_response, tenant_response, cfg.dynamic_facts)


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


def generate_target(
    inv: Inventory,
    target: str,
    components: dict[str, Component],
    classes: list[str],
    component: str,
):
    """This function generates an object which is suitable to be marshalled into YAML as
    a Kapitan target. In contrast to `render_target`, this function doesn't try to infer
    the contents of field `classes`, but instead allows the caller to provide a list of
    classes to include. Note that the contents of `classes` aren't validated by this
    function."""
    bootstrap = target == inv.bootstrap_target

    parameters: dict[str, Union[dict, str]] = {
        "_instance": target,
    }
    if not bootstrap:
        parameters["_base_directory"] = str(
            components[component].alias_directory(target)
        )
        parameters["_kustomize_wrapper"] = str(__kustomize_wrapper__)
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


def render_target(
    inv: Inventory,
    target: str,
    components: dict[str, Component],
    component: Optional[str] = None,
):
    if not component:
        component = target
    bootstrap = target == inv.bootstrap_target
    if not bootstrap and component not in components:
        raise click.ClickException(f"Target {target} is not a component")

    classes = [f"params.{inv.bootstrap_target}"]

    for c in sorted(components):
        defaults_file = inv.defaults_file(c)
        if c == component and target != component:
            # Special case alias defaults symlink
            defaults_file = inv.defaults_file(target)

        if defaults_file.is_file():
            classes.append(f"defaults.{defaults_file.stem}")
        else:
            click.secho(f" > Default file for class {c} missing", fg="yellow")

    classes.append("global.commodore")

    if not bootstrap:
        if not inv.component_file(target).is_file():
            raise click.ClickException(
                f"Target rendering failed for {target}: component class is missing"
            )
        classes.append(f"components.{target}")

    return generate_target(inv, target, components, classes, component)


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


class CompileMeta:
    def __init__(self, cfg: Config):
        self.build_info = {"version": __version__, "gitVersion": __git_version__}
        self.instances = cfg.get_component_alias_versioninfos()
        self.packages = cfg.get_package_versioninfos()
        self.global_repo = cfg.global_version_info
        self.tenant_repo = cfg.tenant_version_info
        self.timestamp = datetime.now().astimezone(None)

    def as_dict(self):
        return {
            "commodoreBuildInfo": self.build_info,
            "global": self.global_repo.as_dict(),
            "instances": {
                a: info.as_dict() for a, info in sorted(self.instances.items())
            },
            "lastCompile": self.timestamp.isoformat(timespec="milliseconds"),
            "packages": {
                p: info.as_dict() for p, info in sorted(self.packages.items())
            },
            "tenant": self.tenant_repo.as_dict(),
        }

    def render_catalog_commit_message(self) -> str:
        component_commits = [
            info.pretty_print(i) for i, info in sorted(self.instances.items())
        ]
        component_commits_str = "\n".join(component_commits)

        package_commits = [
            info.pretty_print(p) for p, info in sorted(self.packages.items())
        ]
        package_commits_str = "\n".join(package_commits)

        config_commits = [
            self.global_repo.pretty_print("global"),
            self.tenant_repo.pretty_print("tenant"),
        ]
        config_commits_str = "\n".join(config_commits)

        return f"""Automated catalog update from Commodore

Component instance commits:
{component_commits_str}

Package commits:
{package_commits_str}

Configuration commits:
{config_commits_str}

Compilation timestamp: {self.timestamp.isoformat(timespec="milliseconds")}
"""


def report_compile_metadata(
    cfg: Config, compile_meta: CompileMeta, cluster_id: str, report=False
):
    if cfg.verbose:
        if report:
            action = "will be reported to Lieutenant"
        else:
            action = "would be reported to Lieutenant on a successful catalog push"
        click.echo(
            f" > The following compile metadata {action}:\n"
            + textwrap.indent(json.dumps(compile_meta.as_dict(), indent=2), "    "),
        )

    if report:
        if cfg.api_token is None:
            # Re-login to ensure we have a valid API token. This assumes that the only case where we
            # call `report_compile_metadata()` and the api_token is None is when a short-lived OIDC
            # token expired while we were compiling the catalog.
            login(cfg)
        lieutenant_post(
            cfg.api_url,
            cfg.api_token,
            f"clusters/{cluster_id}",
            "compileMeta",
            post_data=compile_meta.as_dict(),
        )
