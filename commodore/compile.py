from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import click

from .catalog import fetch_catalog, clean_catalog, update_catalog
from .cluster import (
    Cluster,
    load_cluster_from_api,
    read_cluster_and_tenant,
    update_params,
    update_target,
)
from .config import Config
from .dependency_mgmt import (
    fetch_components,
    fetch_packages,
    register_components,
    register_packages,
    verify_version_overrides,
)
from .dependency_mgmt.component_library import create_component_library_aliases
from .dependency_mgmt.jsonnet_bundler import (
    fetch_jsonnet_libraries,
    jsonnet_dependencies,
)
from .gitrepo import GitRepo
from .helpers import (
    ApiError,
    clean_working_tree,
    kapitan_compile,
    kapitan_inventory,
    rm_tree_contents,
)
from .inventory.lint import check_removed_reclass_variables
from .postprocess import postprocess_components
from .refs import update_refs


def check_removed_reclass_variables_inventory(config: Config, tenant: str):
    paths = [
        # global defaults
        config.inventory.global_config_dir,
        # tenant repo
        config.inventory.tenant_config_dir(tenant),
    ]

    check_removed_reclass_variables(config, "hierarchy", paths)


def check_removed_reclass_variables_components(config: Config):
    paths: Iterable[Path] = sum(
        # defaults.yml and <component-name>.yml for all enabled components
        [[c.defaults_file, c.class_file] for c in config.get_components().values()],
        [],
    )

    check_removed_reclass_variables(config, "enabled components", paths)


def _fetch_global_config(cfg: Config, cluster: Cluster):
    click.secho("Updating global config...", bold=True)
    repo = GitRepo(cluster.global_git_repo_url, cfg.inventory.global_config_dir)
    rev = cluster.global_git_repo_revision
    if cfg.global_repo_revision_override:
        rev = cfg.global_repo_revision_override
    repo.checkout(rev)
    cfg.register_config("global", repo)


def _fetch_customer_config(cfg: Config, cluster: Cluster):
    click.secho("Updating customer config...", bold=True)
    repo_url = cluster.config_repo_url
    if cfg.debug:
        click.echo(f" > Cloning customer config {repo_url}")
    repo = GitRepo(repo_url, cfg.inventory.tenant_config_dir(cluster.tenant_id))
    rev = cluster.config_git_repo_revision
    if cfg.tenant_repo_revision_override:
        rev = cfg.tenant_repo_revision_override
    repo.checkout(rev)
    cfg.register_config("customer", repo)


def _regular_setup(config: Config, cluster_id):
    try:
        cluster = load_cluster_from_api(config, cluster_id)
    except ApiError as e:
        raise click.ClickException(f"While fetching cluster specification: {e}") from e

    update_target(config, config.inventory.bootstrap_target)
    update_params(config.inventory, cluster)

    # Fetch components and config
    _fetch_global_config(config, cluster)
    _fetch_customer_config(config, cluster)
    check_removed_reclass_variables_inventory(config, cluster.tenant_id)

    # Fetch component config packages. This needs to happen before component fetching
    # because we want to be able to discover components included by config packages.
    fetch_packages(config)

    fetch_components(config)

    update_target(config, config.inventory.bootstrap_target)

    for alias, component in config.get_component_aliases().items():
        update_target(config, alias, component=component)

    # Fetch catalog
    return fetch_catalog(config, cluster)


def _local_setup(config: Config, cluster_id):
    click.secho("Running in local mode", bold=True)
    click.echo(" > Will use existing inventory, components, and catalog")
    if not config.fetch_dependencies:
        click.echo(" > Will use existing Jsonnet and Kapitan dependencies")
        click.echo(
            "   > Use --fetch-dependencies at least once if you're trying to enable a new component in local mode,"
            + " otherwise Kapitan will fail to find the component"
        )

    file = config.inventory.target_file(config.inventory.bootstrap_target)
    if not file.is_file():
        raise click.ClickException(f"Invalid working dir state: '{file}' is missing")

    click.echo(" > Assert current working dir state matches requested compilation")
    current_cluster_id, tenant = read_cluster_and_tenant(config.inventory)
    if current_cluster_id != cluster_id:
        error = (
            "[Local mode] Cluster ID mismatch: local state targets "
            + f"{current_cluster_id}, compilation was requested for {cluster_id}"
        )
        raise click.ClickException(error)

    click.secho("Registering config...", bold=True)
    config.register_config("global", GitRepo(None, config.inventory.global_config_dir))
    config.register_config(
        "customer", GitRepo(None, config.inventory.tenant_config_dir(tenant))
    )

    check_removed_reclass_variables_inventory(config, tenant)

    click.secho("Resetting targets...", bold=True)
    rm_tree_contents(config.inventory.targets_dir)

    click.secho("Resetting component symlinks in inventory...", bold=True)
    rm_tree_contents(config.inventory.defaults_dir)
    rm_tree_contents(config.inventory.components_dir)

    click.secho("Creating bootstrap target...", bold=True)
    update_target(config, config.inventory.bootstrap_target)

    register_packages(config)
    register_components(config)

    for alias, component in config.get_component_aliases().items():
        update_target(config, alias, component=component)
    update_target(config, config.inventory.bootstrap_target)

    click.secho("Configuring catalog repo...", bold=True)
    return GitRepo(None, config.catalog_dir)


def check_parameters_component_versions(cluster_parameters):
    """
    Check inventory for `parameters.component_versions`.

    Raise an error if the parameter has any contents.
    """
    cvers = cluster_parameters.get("component_versions", {})
    if len(cvers.keys()) > 0:
        raise click.ClickException(
            "Specifying component versions in parameter `component_versions` "
            + "is no longer suppported. Please migrate your configuration to "
            + "parameter `components`."
        )


def setup_compile_environment(config: Config) -> tuple[dict[str, Any], Iterable[str]]:
    # Raise error if any enabled components use removed reclass variables
    check_removed_reclass_variables_components(config)

    inventory = kapitan_inventory(config)
    cluster_parameters = inventory[config.inventory.bootstrap_target]["parameters"]
    check_parameters_component_versions(cluster_parameters)
    create_component_library_aliases(config, cluster_parameters)

    # Verify that all aliased components support instantiation
    config.verify_component_aliases(cluster_parameters)
    config.register_component_deprecations(cluster_parameters)
    # Raise exception if component version override without URL is present in the
    # hierarchy.
    verify_version_overrides(cluster_parameters)

    for component in config.get_components().values():
        ckey = component.parameters_key
        component.render_jsonnetfile_json(cluster_parameters[ckey])

    if config.fetch_dependencies:
        fetch_jsonnet_libraries(config.work_dir, deps=jsonnet_dependencies(config))

    aliases = config.get_component_aliases()

    # Generate Kapitan secret references from refs found in inventory
    # parameters
    update_refs(config, aliases, inventory)

    return inventory, list(aliases.keys())


# pylint: disable=redefined-builtin
def compile(config, cluster_id):
    if config.local:
        catalog_repo = _local_setup(config, cluster_id)
    else:
        clean_working_tree(config)
        catalog_repo = _regular_setup(config, cluster_id)

    inventory, targets = setup_compile_environment(config)

    clean_catalog(catalog_repo)

    kapitan_compile(config, targets, search_paths=[config.vendor_dir])

    postprocess_components(config, inventory, config.get_components())

    update_catalog(config, targets, catalog_repo)

    click.secho("Catalog compiled! 🎉", bold=True)

    config.print_deprecation_notices()
