import click
from kapitan.resources import inventory_reclass
from pathlib import Path as P

from . import git
from .catalog import (
    fetch_customer_catalog,
    update_catalog
)
from .dependency_mgmt import (
    fetch_components,
    fetch_jsonnet_libs,
    set_component_versions
)
from .helpers import (
    clean,
    api_request,
    kapitan_compile,
    ApiError
)
from .postprocess import postprocess_components
from .refs import update_refs
from .target import update_target


def _fetch_cluster_spec(cfg, customer, cluster):
    return api_request(cfg.api_url, 'inventory', customer, cluster)


def _fetch_global_config(cfg, response):
    config = response['global']['config']
    click.secho(f"Updating global config...", bold=True)
    repo = git.clone_repository(
        f"{cfg.global_git_base}/{config}.git",
        'inventory/classes/global')
    cfg.register_config('global', repo)


def _fetch_customer_config(cfg, repopath, customer):
    if repopath is None:
        repopath = f"{cfg.customer_git_base}/{customer}.git"
    click.secho('Updating customer config...', bold=True)
    repo = git.clone_repository(repopath, P('inventory/classes') / customer)
    cfg.register_config('customer', repo)


def _regular_setup(config, customer, cluster):
    try:
        inv = _fetch_cluster_spec(config, customer, cluster)
    except ApiError as e:
        raise click.ClickException(f"While fetching cluster specification: {e}") from e

    # Fetch components and config
    try:
        _fetch_global_config(config, inv)
        _fetch_customer_config(config, inv['cluster'].get('override', None), customer)
        fetch_components(config)
    except Exception as e:
        raise click.ClickException(f"While cloning git repositories: {e}") from e

    target_name = update_target(config, customer, cluster, inv['catalog_repo'])
    if target_name != 'cluster':
        raise click.ClickException(
            f"Only target with name 'cluster' is supported, got {target_name}")

    # Fetch catalog
    try:
        catalog_repo = fetch_customer_catalog(config, target_name, inv['catalog_repo'])
    except Exception as e:
        raise click.ClickException(f"While cloning git repositories: {e}") from e

    return target_name, catalog_repo


def _local_setup(config, customer, cluster):
    click.secho('Running in local mode', bold=True)
    click.echo(' > Will use existing inventory, dependencies, and catalog')
    # Currently, a target name other than "cluster" is not supported
    target_name = 'cluster'
    target_yml = P('inventory/targets') / f"{target_name}.yml"
    if not target_yml.is_file():
        raise click.ClickException(f"Invalid target: {target_name}")
    click.echo(f" > Using target: {target_name}")

    click.secho('Registering config...', bold=True)
    config.register_config('global',
                           git.init_repository('inventory/classes/global'))
    config.register_config('customer',
                           git.init_repository(P('inventory/classes/') / customer))

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

    return target_name, catalog_repo


def compile(config, customer, cluster):
    if config.local:
        target_name, catalog_repo = _local_setup(config, customer, cluster)
    else:
        clean(config)
        target_name, catalog_repo = _regular_setup(config, customer, cluster)

    # Compile kapitan inventory to extract component versions. Component
    # versions are assumed to be defined in the inventory key
    # 'parameters.component_versions'
    kapitan_inventory = inventory_reclass('inventory')['nodes'][target_name]
    versions = kapitan_inventory['parameters'].get('component_versions', None)
    if versions and not config.local:
        set_component_versions(config, versions)
        update_target(config, customer, cluster,
                list(catalog_repo.remote('origin').urls)[0])

    jsonnet_libs = kapitan_inventory['parameters'].get(
        'commodore', {}).get('jsonnet_libs', None)
    if jsonnet_libs and not config.local:
        fetch_jsonnet_libs(config, jsonnet_libs)

    # Generate Kapitan secret references from refs found in inventory
    # parameters
    update_refs(config, kapitan_inventory['parameters'])

    p = kapitan_compile()
    if p.returncode != 0:
        raise click.ClickException(f"Catalog compilation failed")

    postprocess_components(kapitan_inventory, target_name, config.get_components())

    update_catalog(config, target_name, catalog_repo)

    click.secho('Catalog compiled! 🎉', bold=True)
