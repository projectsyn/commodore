from pathlib import Path as P

import click
from kapitan.cached import reset_cache as reset_reclass_cache
from kapitan.resources import inventory_reclass

from . import git
from .catalog import fetch_customer_catalog, clean_catalog, update_catalog
from .cluster import (
    BOOTSTRAP_TARGET,
    Cluster,
    load_cluster_from_api,
    read_cluster_and_tenant,
    update_params,
    update_target,
)
from .config import Config
from .dependency_mgmt import (
    fetch_components,
    fetch_jsonnet_libs,
    fetch_jsonnet_libraries,
    register_components,
    set_component_overrides,
    write_jsonnetfile,
    jsonnet_dependencies,
)
from .helpers import (
    ApiError,
    clean_working_tree,
    kapitan_compile,
)
from .postprocess import postprocess_components
from .refs import update_refs


def _fetch_global_config(cfg: Config, cluster: Cluster):
    click.secho("Updating global config...", bold=True)
    repo = git.clone_repository(
        cluster.global_git_repo_url, cfg.inventory.global_config_dir, cfg
    )
    rev = cluster.global_git_repo_revision
    if rev:
        git.checkout_version(repo, rev)
    cfg.register_config("global", repo)


def _fetch_customer_config(cfg: Config, cluster: Cluster):
    click.secho("Updating customer config...", bold=True)
    repo_url = cluster.config_repo_url
    if cfg.debug:
        click.echo(f" > Cloning customer config {repo_url}")
    repo = git.clone_repository(
        repo_url, cfg.inventory.tenant_config_dir(cluster.tenant), cfg
    )
    rev = cluster.config_git_repo_revision
    if rev:
        git.checkout_version(repo, rev)
    cfg.register_config("customer", repo)


def _regular_setup(config, cluster_id):
    try:
        cluster = load_cluster_from_api(config, cluster_id)
    except ApiError as e:
        raise click.ClickException(f"While fetching cluster specification: {e}") from e

    update_target(config, BOOTSTRAP_TARGET, bootstrap=True)
    update_params(cluster)

    # Fetch components and config
    _fetch_global_config(config, cluster)
    _fetch_customer_config(config, cluster)
    fetch_components(config)

    update_target(config, BOOTSTRAP_TARGET, bootstrap=True)
    for component in config.get_components().keys():
        update_target(config, component)

    # Fetch catalog
    return fetch_customer_catalog(config, cluster)


def _local_setup(config: Config, cluster_id):
    click.secho("Running in local mode", bold=True)
    click.echo(" > Will use existing inventory, dependencies, and catalog")

    file = config.inventory.target_file(BOOTSTRAP_TARGET)
    if not file.is_file():
        raise click.ClickException(f"Invalid working dir state: '{file}' is missing")

    click.echo(" > Assert current working dir state matches requested compilation")
    current_cluster_id, tenant = read_cluster_and_tenant()
    if current_cluster_id != cluster_id:
        error = (
            "[Local mode] Cluster ID mismatch: local state targets "
            + f"{current_cluster_id}, compilation was requested for {cluster_id}"
        )
        raise click.ClickException(error)

    click.secho("Registering config...", bold=True)
    config.register_config(
        "global", git.init_repository(config.inventory.global_config_dir)
    )
    config.register_config(
        "customer", git.init_repository(config.inventory.tenant_config_dir(tenant))
    )

    register_components(config)

    click.secho("Configuring catalog repo...", bold=True)
    return git.init_repository("catalog")


# pylint: disable=redefined-builtin
def compile(config, cluster_id):
    if config.local:
        catalog_repo = _local_setup(config, cluster_id)
    else:
        clean_working_tree(config)
        catalog_repo = _regular_setup(config, cluster_id)

    # Compile kapitan inventory to extract component versions. Component
    # versions are assumed to be defined in the inventory key
    # 'parameters.component_versions'
    reset_reclass_cache()
    cluster_inventory = inventory_reclass("inventory")["nodes"][BOOTSTRAP_TARGET]
    versions = cluster_inventory["parameters"].get("component_versions", None)
    if versions and not config.local:
        set_component_overrides(config, versions)
    # Rebuild reclass inventory to use new version of components
    reset_reclass_cache()
    kapitan_inventory = inventory_reclass("inventory")["nodes"]
    jsonnet_libs = (
        kapitan_inventory[BOOTSTRAP_TARGET]["parameters"]
        .get("commodore", {})
        .get("jsonnet_libs", None)
    )
    if jsonnet_libs and not config.local:
        fetch_jsonnet_libs(config, jsonnet_libs)

    if not config.local:
        write_jsonnetfile(P("jsonnetfile.json"), jsonnet_dependencies(config))
        fetch_jsonnet_libraries()

    clean_catalog(catalog_repo)

    # Generate Kapitan secret references from refs found in inventory
    # parameters
    update_refs(config, kapitan_inventory[BOOTSTRAP_TARGET]["parameters"])

    components = config.get_components()
    component_names = components.keys()
    kapitan_compile(config, component_names, search_paths=["./vendor/"])

    postprocess_components(config, kapitan_inventory, components)

    update_catalog(config, component_names, catalog_repo)

    click.secho("Catalog compiled! 🎉", bold=True)
