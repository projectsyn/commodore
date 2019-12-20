import click
import os

from .helpers import (
    api_request,
    ApiError,
    yaml_dump
)

from pathlib import Path as P


def fetch_target(cfg, customer, cluster):
    return api_request(cfg.api_url, 'targets', customer, cluster)


def _full_target(customer, cluster, apidata, components, catalog):
    cloud_provider = apidata['cloud_type']
    cloud_region = apidata['cloud_region']
    cluster_distro = apidata['cluster_distribution']
    component_defaults = [f"defaults.{cn}" for cn in components if
                          (P('inventory/classes/defaults') / f"{cn}.yml").is_file()]
    return {
        'classes': component_defaults + [
            'global.common',
            f"global.{cluster_distro}",
            f"global.{cloud_provider}",
            f"global.{cloud_provider}.{cloud_region}",
            f"{customer}.{cluster}"
        ],
        'parameters': {
            'target_name': 'cluster',
            'cluster': {
                'name': f"{cluster}",
                'dist': f"{cluster_distro}",
                'catalog_url': f"{catalog}",
            },
            'cloud': {
                'type': f"{cloud_provider}",
                'region': f"{cloud_region}",
            },
            'customer': {
                'name': f"{customer}"
            },
        }
    }


def update_target(cfg, customer, cluster, catalog):
    click.secho('Updating Kapitan target...', bold=True)
    try:
        target = fetch_target(cfg, customer, cluster)
    except ApiError as e:
        raise click.ClickException(f"While fetching target: {e}") from e

    os.makedirs('inventory/targets', exist_ok=True)
    yaml_dump(_full_target(customer, cluster, target,
                           cfg.get_components().keys(), catalog),
              'inventory/targets/cluster.yml')

    return 'cluster'
