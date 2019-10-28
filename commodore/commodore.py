import click, json, os
from kapitan.resources import inventory_reclass

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
        ApiError,
        rm_tree_contents,
        yaml_dump
    )
from .postprocess import postprocess_components

def fetch_cluster_spec(cfg, customer, cluster):
    return api_request(cfg.api_url, 'inventory', customer, cluster)

def fetch_config(cfg, response):
    config = response['global']['config']
    click.secho(f"Updating global config...", bold=True)
    repo = git.clone_repository(f"{cfg.global_git_base}/{config}.git", f"inventory/classes/global")
    cfg.register_config('global', repo)

def fetch_target(cfg, customer, cluster):
    return api_request(cfg.api_url, 'targets', customer, cluster)

def _full_target(customer, cluster, apidata):
    cloud_type = apidata['cloud_type']
    cloud_region = apidata['cloud_region']
    cluster_distro = apidata['cluster_distribution']
    return {
        "classes": [
            "global.common",
            f"global.{cloud_type}",
            f"global.{cluster_distro}",
            f"{customer}.{cluster}"
        ],
        "parameters": {
            "target_name": "cluster",
            "cluster": {
                "name": f"{cluster}",
                "dist": f"{cluster_distro}"
            },
            "cloud": {
                "type": f"{cloud_type}",
                "region": f"{cloud_region}"
            },
            "customer": {
                "name": f"{customer}"
            }
        }
    }

def update_target(cfg, customer, cluster):
    click.secho("Updating Kapitan target...", bold=True)
    try:
        target = fetch_target(cfg, customer, cluster)
    except ApiError as e:
        raise click.ClickException(f"While fetching target: {e}") from e

    os.makedirs('inventory/targets', exist_ok=True)
    yaml_dump(_full_target(customer, cluster, target),
            'inventory/targets/cluster.yml')

    return 'cluster'

def fetch_customer_config(cfg, repo, customer):
    if repo is None:
        repo = f"{cfg.customer_git_base}/{customer}.git"
    click.secho("Updating customer config...", bold=True)
    repo = git.clone_repository(repo, f"inventory/classes/{customer}")
    cfg.register_config('customer', repo)

def compile(config, customer, cluster):
    if config.local:
        click.secho("Running in local mode", bold=True)
        click.echo(" > Will use existing inventory, dependencies, and catalog")
        target_name = config.local
        if not os.path.isfile(f"inventory/targets/{target_name}.yml"):
            raise click.ClickException(f"Invalid target: {target_name}")
        click.echo(f" > Using target: {target_name}")
        click.secho("Registering components...", bold=True)
        for c in os.listdir('dependencies'):
            # Skip jsonnet libs when collecting components
            if c == "lib" or c == "libs":
                continue
            click.echo(f" > {c}")
            repo = git.init_repository(f"dependencies/{c}")
            config.register_component(c, repo)
        click.secho("Configuring catalog repo...", bold=True)
        catalog_repo = git.init_repository(f"catalog")
    else:
        clean(config)

        try:
            inv = fetch_cluster_spec(config, customer, cluster)
        except ApiError as e:
            raise click.ClickException(f"While fetching cluster specification: {e}") from e

        target_name = update_target(config, customer, cluster)

        # Fetch all Git repos
        try:
            fetch_config(config, inv)
            fetch_components(config, inv['global']['components'])
            fetch_customer_config(config, inv['cluster'].get('override', None), customer)
            fetch_jsonnet_libs(config, inv['global']['jsonnet_libs'])
            catalog_repo = fetch_customer_catalog(config, target_name, inv['catalog_repo'])
        except Exception as e:
            raise click.ClickException(f"While cloning git repositories: {e}") from e

    # Compile kapitan inventory to extract component versions. Component
    # versions are assumed to be defined in the inventory key
    # 'parameters.component_versions'
    kapitan_inventory = inventory_reclass('inventory')['nodes'][target_name]
    versions = kapitan_inventory['parameters'].get('component_versions', None)
    if versions and not config.local:
        set_component_versions(config, versions)

    p = kapitan_compile()
    if p.returncode != 0:
        raise click.ClickException(f"Catalog compilation failed")

    postprocess_components(kapitan_inventory, target_name, config.get_components())

    update_catalog(config, target_name, catalog_repo)

    click.secho("Catalog compiled! 🎉", bold=True)
