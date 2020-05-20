from pathlib import Path as P

import click
from kapitan.resources import inventory_reclass

from . import git
from .catalog import (
    fetch_customer_catalog,
    clean_catalog,
    update_catalog
)
from .cluster import (
    fetch_cluster,
    reconstruct_api_response,
    update_target,
)
from .dependency_mgmt import (
    fetch_components,
    fetch_jsonnet_libs,
    set_component_versions
)
from .helpers import (
    ApiError,
    clean,
    kapitan_compile,
    lieutenant_query,
)
from .postprocess import postprocess_components
from .refs import update_refs


def _fetch_global_config(cfg, cluster):
    config = cluster['base_config']
    click.secho('Updating global config...', bold=True)
    repo = git.clone_repository(
        f"{cfg.global_git_base}/{config}.git",
        'inventory/classes/global')
    cfg.register_config('global', repo)


def _fetch_customer_config(cfg, customer_id):
    click.secho('Updating customer config...', bold=True)
    customer = lieutenant_query(cfg.api_url, cfg.api_token, 'tenants', customer_id)
    if customer['id'] != customer_id:
        raise click.ClickException("Customer id mismatch")
    repopath = customer.get('gitRepo', {}).get('url', None)
    if repopath is None:
        raise click.ClickException(
            f" > API did not return a repository URL for customer '{customer_id}'")
    click.echo(f"Cloning {repopath}")
    repo = git.clone_repository(repopath, P('inventory/classes') / customer_id)
    cfg.register_config('customer', repo)


def _regular_setup(config, cluster_id):
    try:
        cluster = fetch_cluster(config, cluster_id)
    except ApiError as e:
        raise click.ClickException(f"While fetching cluster specification: {e}") from e
    customer_id = cluster['tenant']

    # Fetch components and config
    _fetch_global_config(config, cluster)
    _fetch_customer_config(config, customer_id)
    fetch_components(config)
    target_name = update_target(config, cluster)
    if target_name != 'cluster':
        raise click.ClickException(
            f"Only target with name 'cluster' is supported, got {target_name}")

    # Fetch catalog
    catalog_repo = fetch_customer_catalog(cluster['gitRepo'])

    return cluster, target_name, catalog_repo


def _local_setup(config, cluster_id):
    click.secho('Running in local mode', bold=True)
    click.echo(' > Will use existing inventory, dependencies, and catalog')
    # Currently, a target name other than "cluster" is not supported
    target_name = 'cluster'
    target_yml = P('inventory/targets') / f"{target_name}.yml"
    if not target_yml.is_file():
        raise click.ClickException(f"Invalid target: {target_name}")
    click.echo(f" > Using target: {target_name}")

    click.echo(' > Reconstructing Cluster API data from target')
    cluster = reconstruct_api_response(target_yml)
    if cluster['id'] != cluster_id:
        error = '[Local mode] Cluster ID mismatch: local state targets ' + \
                f"{cluster['id']}, compilation was requested for {cluster_id}"
        raise click.ClickException(error)

    customer_id = cluster['tenant']

    click.secho('Registering config...', bold=True)
    config.register_config('global',
                           git.init_repository('inventory/classes/global'))
    config.register_config('customer',
                           git.init_repository(P('inventory/classes/') /
                                               customer_id))

    click.secho('Registering components...', bold=True)
    for c in P('dependencies').iterdir():
        # Skip jsonnet libs when collecting components
        if c.name == 'lib' or c.name == 'libs':
            continue
        click.echo(f" > {c}")
        repo = git.init_repository(c)
        config.register_component(c.name, repo)

    click.secho('Configuring catalog repo...', bold=True)
    catalog_repo = git.init_repository('catalog')

    return cluster, target_name, catalog_repo


# pylint: disable=redefined-builtin
def compile(config, cluster_id):
    if config.local:
        cluster, target_name, catalog_repo = _local_setup(config, cluster_id)
    else:
        clean(config)
        cluster, target_name, catalog_repo = _regular_setup(config, cluster_id)

    # Compile kapitan inventory to extract component versions. Component
    # versions are assumed to be defined in the inventory key
    # 'parameters.component_versions'
    kapitan_inventory = inventory_reclass('inventory')['nodes'][target_name]
    versions = kapitan_inventory['parameters'].get('component_versions', None)
    if versions and not config.local:
        set_component_versions(config, versions)
        update_target(config, cluster)

    jsonnet_libs = kapitan_inventory['parameters'].get(
        'commodore', {}).get('jsonnet_libs', None)
    if jsonnet_libs and not config.local:
        fetch_jsonnet_libs(jsonnet_libs)

    clean_catalog(catalog_repo)

    # Generate Kapitan secret references from refs found in inventory
    # parameters
    update_refs(config, kapitan_inventory['parameters'])

    p = kapitan_compile()
    if p.returncode != 0:
        raise click.ClickException('Kapitan catalog compilation failed.')

    postprocess_components(kapitan_inventory, target_name, config.get_components())

    update_catalog(config, target_name, catalog_repo)

    click.secho('Catalog compiled! 🎉', bold=True)
