from pathlib import Path as P

import click
from kapitan.cached import reset_cache as reset_reclass_cache
from kapitan.resources import inventory_reclass

from . import git
from .catalog import fetch_customer_catalog, clean_catalog, update_catalog
from .cluster import (
    Cluster,
    load_cluster_from_api,
    read_cluster_and_tenant,
    target_file,
    update_params,
    update_target,
)
from .config import Component
from .dependency_mgmt import (
    fetch_components,
    fetch_jsonnet_libs,
    fetch_jsonnet_libraries,
    set_component_overrides,
    write_jsonnetfile,
)
from .helpers import (
    ApiError,
    clean_working_tree,
    kapitan_compile,
)
from .postprocess import postprocess_components
from .refs import update_refs


TARGET = "cluster"


def _fetch_global_config(cfg, cluster: Cluster):
    click.secho("Updating global config...", bold=True)
    repo = git.clone_repository(
        cluster.global_git_repo_url, "inventory/classes/global", cfg
    )
    rev = cluster.global_git_repo_revision
    if rev:
        git.checkout_version(repo, rev)
    cfg.register_config("global", repo)


def _fetch_customer_config(cfg, cluster: Cluster):
    click.secho("Updating customer config...", bold=True)
    repo_url = cluster.config_repo_url
    if cfg.debug:
        click.echo(f" > Cloning customer config {repo_url}")
    repo = git.clone_repository(repo_url, P("inventory/classes") / cluster.tenant, cfg)
    rev = cluster.config_git_repo_revision
    if rev:
        git.checkout_version(repo, rev)
    cfg.register_config("customer", repo)


def _regular_setup(config, cluster_id, target):
    try:
        cluster = load_cluster_from_api(config, cluster_id)
    except ApiError as e:
        raise click.ClickException(f"While fetching cluster specification: {e}") from e

    update_target(config, target)
    update_params(cluster, target)

    # Fetch components and config
    _fetch_global_config(config, cluster)
    _fetch_customer_config(config, cluster)
    fetch_components(config)
    update_target(config, target)

    # Fetch catalog
    return fetch_customer_catalog(config, cluster)


def _local_setup(config, cluster_id, target):
    click.secho("Running in local mode", bold=True)
    click.echo(" > Will use existing inventory, dependencies, and catalog")

    # Currently, a target name other than "cluster" is not supported
    if not target_file(target).is_file():
        raise click.ClickException(f"Invalid target: {target}")
    click.echo(f" > Using target: {target}")

    click.echo(" > Assert current target matches")
    current_cluster_id, tenant = read_cluster_and_tenant(target)
    if current_cluster_id != cluster_id:
        error = (
            "[Local mode] Cluster ID mismatch: local state targets "
            + f"{current_cluster_id}, compilation was requested for {cluster_id}"
        )
        raise click.ClickException(error)

    click.secho("Registering config...", bold=True)
    config.register_config("global", git.init_repository("inventory/classes/global"))
    config.register_config(
        "customer", git.init_repository(P("inventory/classes/") / tenant)
    )

    click.secho("Registering components...", bold=True)
    for c in P("dependencies").iterdir():
        # Skip jsonnet libs when collecting components
        if c.name == "lib" or c.name == "libs":
            continue
        if config.debug:
            click.echo(f" > {c}")
        repo = git.init_repository(c)
        component = Component(
            name=c.name,
            repo=repo,
            version="master",
            repo_url=repo.remotes.origin.url,
        )
        config.register_component(component)

    click.secho("Configuring catalog repo...", bold=True)
    return git.init_repository("catalog")


# pylint: disable=redefined-builtin
def compile(config, cluster_id):
    if config.local:
        catalog_repo = _local_setup(config, cluster_id, TARGET)
    else:
        clean_working_tree(config)
        catalog_repo = _regular_setup(config, cluster_id, TARGET)

    # Compile kapitan inventory to extract component versions. Component
    # versions are assumed to be defined in the inventory key
    # 'parameters.component_versions'
    reset_reclass_cache()
    kapitan_inventory = inventory_reclass("inventory")["nodes"][TARGET]
    versions = kapitan_inventory["parameters"].get("component_versions", None)
    if versions and not config.local:
        set_component_overrides(config, versions)
        update_target(config, TARGET)
    # Rebuild reclass inventory to use new version of components
    reset_reclass_cache()
    kapitan_inventory = inventory_reclass("inventory")["nodes"][TARGET]
    jsonnet_libs = (
        kapitan_inventory["parameters"].get("commodore", {}).get("jsonnet_libs", None)
    )
    if jsonnet_libs and not config.local:
        fetch_jsonnet_libs(config, jsonnet_libs)

    if not config.local:
        write_jsonnetfile(config)
        fetch_jsonnet_libraries()

    clean_catalog(catalog_repo)

    # Generate Kapitan secret references from refs found in inventory
    # parameters
    update_refs(config, kapitan_inventory["parameters"])

    kapitan_compile(config, search_paths=["./vendor/"])

    postprocess_components(config, kapitan_inventory, TARGET, config.get_components())

    update_catalog(config, TARGET, catalog_repo)

    click.secho("Catalog compiled! 🎉", bold=True)
