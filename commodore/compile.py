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
    rm_tree_contents,
)
from .postprocess import postprocess_components
from .refs import update_refs


def _fetch_global_config(cfg: Config, cluster: Cluster):
    click.secho("Updating global config...", bold=True)
    repo = git.clone_repository(
        cluster.global_git_repo_url, cfg.inventory.global_config_dir, cfg
    )
    rev = cluster.global_git_repo_revision
    if cfg.global_repo_revision_override:
        rev = cfg.global_repo_revision_override
    if rev:
        git.checkout_version(repo, rev)
    cfg.register_config("global", repo)


def _fetch_customer_config(cfg: Config, cluster: Cluster):
    click.secho("Updating customer config...", bold=True)
    repo_url = cluster.config_repo_url
    if cfg.debug:
        click.echo(f" > Cloning customer config {repo_url}")
    repo = git.clone_repository(
        repo_url, cfg.inventory.tenant_config_dir(cluster.tenant_id), cfg
    )
    rev = cluster.config_git_repo_revision
    if cfg.tenant_repo_revision_override:
        rev = cfg.tenant_repo_revision_override
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
    config.register_config(
        "global", git.init_repository(config.inventory.global_config_dir)
    )
    config.register_config(
        "customer", git.init_repository(config.inventory.tenant_config_dir(tenant))
    )

    click.secho("Resetting targets...", bold=True)
    rm_tree_contents(config.inventory.targets_dir)

    click.secho("Resetting component symlinks in inventory...", bold=True)
    rm_tree_contents(config.inventory.defaults_dir)
    rm_tree_contents(config.inventory.components_dir)

    click.secho("Creating bootstrap target...", bold=True)
    update_target(config, config.inventory.bootstrap_target)

    register_components(config)

    for alias, component in config.get_component_aliases().items():
        update_target(config, alias, component=component)
    update_target(config, config.inventory.bootstrap_target)

    click.secho("Configuring catalog repo...", bold=True)
    return git.init_repository(config.catalog_dir)


def check_parameters_component_versions(config: Config, cluster_parameters):
    """
    Deprecation handler for `parameters.component_versions`.

    Registers a deprecation notice if uses of `parameters.component_versions`
    are found in the rendered inventory.
    """
    cvers = cluster_parameters.get("component_versions", {})
    if len(cvers.keys()) > 0:
        config.register_deprecation_notice(
            "`parameters.component_versions` is deprecated, please migrate to `parameters.components`"
        )


# pylint: disable=redefined-builtin
def compile(config, cluster_id):
    if config.local:
        catalog_repo = _local_setup(config, cluster_id)
    else:
        clean_working_tree(config)
        catalog_repo = _regular_setup(config, cluster_id)

    inventory = kapitan_inventory(config)
    cluster_parameters = inventory[config.inventory.bootstrap_target]["parameters"]
    check_parameters_component_versions(config, cluster_parameters)

    # Verify that all aliased components support instantiation
    config.verify_component_aliases(cluster_parameters)
    config.register_component_deprecations(cluster_parameters)

    for component in config.get_components().values():
        ckey = component.parameters_key
        component.render_jsonnetfile_json(cluster_parameters[ckey])

    jsonnet_libs = cluster_parameters.get("commodore", {}).get("jsonnet_libs", None)
    if jsonnet_libs and config.fetch_dependencies:
        config.register_deprecation_notice(
            "Parameter `commodore.jsonnet_libs` is deprecated. "
            + "If your component needs Jsonnet dependencies, specify them in the component's `jsonnetfile.json`"
        )
        fetch_jsonnet_libs(config, jsonnet_libs)

    if config.fetch_dependencies:
        fetch_jsonnet_libraries(config.work_dir, deps=jsonnet_dependencies(config))

    clean_catalog(catalog_repo)

    components = config.get_components()
    aliases = config.get_component_aliases()
    targets = list(aliases.keys())

    # Generate Kapitan secret references from refs found in inventory
    # parameters
    update_refs(config, aliases, inventory)

    kapitan_compile(
        config,
        targets,
        search_paths=[config.vendor_dir],
        fetch_dependencies=config.fetch_dependencies,
    )

    postprocess_components(config, inventory, components)

    update_catalog(config, targets, catalog_repo)

    click.secho("Catalog compiled! 🎉", bold=True)

    config.print_deprecation_notices()
