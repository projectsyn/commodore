import click

from . import git
from .catalog import fetch_customer_catalog, clean_catalog, update_catalog
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
    fetch_jsonnet_libs,
    fetch_jsonnet_libraries,
    register_components,
    jsonnet_dependencies,
)
from .helpers import (
    ApiError,
    clean_working_tree,
    kapitan_compile,
    kapitan_inventory,
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
    fetch_components(config)

    update_target(config, config.inventory.bootstrap_target)

    for alias, component in config.get_component_aliases().items():
        update_target(config, alias, component=component)

    # Fetch catalog
    return fetch_customer_catalog(config, cluster)


def _local_setup(config: Config, cluster_id):
    click.secho("Running in local mode", bold=True)
    click.echo(" > Will use existing inventory, dependencies, and catalog")

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
    config.register_config(
        "global", git.init_repository(config.inventory.global_config_dir)
    )
    config.register_config(
        "customer", git.init_repository(config.inventory.tenant_config_dir(tenant))
    )

    register_components(config)

    click.secho("Configuring catalog repo...", bold=True)
    return git.init_repository(config.catalog_dir)


# pylint: disable=redefined-builtin
def compile(config, cluster_id):
    if config.local:
        catalog_repo = _local_setup(config, cluster_id)
    else:
        clean_working_tree(config)
        catalog_repo = _regular_setup(config, cluster_id)

    inventory = kapitan_inventory(config)
    cluster_parameters = inventory[config.inventory.bootstrap_target]["parameters"]

    # Verify that all aliased components support instantiation
    config.verify_component_aliases(cluster_parameters)

    for component in config.get_components().values():
        ckey = component.parameters_key
        component.render_jsonnetfile_json(cluster_parameters[ckey])

    jsonnet_libs = cluster_parameters.get("commodore", {}).get("jsonnet_libs", None)
    if jsonnet_libs and not config.local:
        fetch_jsonnet_libs(config, jsonnet_libs)

    if not config.local:
        fetch_jsonnet_libraries(config.work_dir, deps=jsonnet_dependencies(config))

    clean_catalog(catalog_repo)

    components = config.get_components()
    aliases = config.get_component_aliases()
    targets = list(aliases.keys())

    # Generate Kapitan secret references from refs found in inventory
    # parameters
    update_refs(config, aliases, inventory)

    kapitan_compile(config, targets, search_paths=[config.vendor_dir])

    postprocess_components(config, inventory, components)

    update_catalog(config, targets, catalog_repo)

    click.secho("Catalog compiled! 🎉", bold=True)

    config.print_deprecation_notices()
