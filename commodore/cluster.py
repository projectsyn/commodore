import os

from pathlib import Path as P

import click

from .helpers import (
    lieutenant_query,
    yaml_dump,
    yaml_load,
)


def fetch_cluster(cfg, clusterid):
    cluster = lieutenant_query(cfg.api_url, cfg.api_token, 'clusters', clusterid)
    # TODO: move Commodore global defaults repo name into Lieutenant
    # API/cluster facts
    cluster['base_config'] = 'commodore-defaults'
    return cluster


def reconstruct_api_response(target_yml):
    target_data = yaml_load(target_yml)['parameters']
    return {
        "id": target_data['cluster']['name'],
        "facts": {
            "cloud": target_data['cloud']['region'],
            "distribution": target_data['cluster']['dist'],
            "region": target_data['cloud']['region'],
        },
        "gitRepo": {
            "url": target_data['cluster']['catalog_url'],
        },
        "tenant": target_data['customer']['name'],
    }


def _full_target(cluster, components, catalog):
    cloud_provider = cluster['facts']['cloud']
    cloud_region = cluster['facts']['region']
    cluster_distro = cluster['facts']['distribution']
    cluster_id = cluster['id']
    customer = cluster['tenant']
    component_defaults = [f"defaults.{cn}" for cn in components if
                          (P('inventory/classes/defaults') / f"{cn}.yml").is_file()]
    return {
        'classes': component_defaults + [
            'global.common',
            f"global.{cluster_distro}",
            f"global.{cloud_provider}",
            f"global.{cloud_provider}.{cloud_region}",
            f"{customer}.{cluster_id}"
        ],
        'parameters': {
            'target_name': 'cluster',
            'cluster': {
                'name': f"{cluster_id}",
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


def update_target(cfg, cluster):
    click.secho('Updating Kapitan target...', bold=True)
    catalog = cluster['gitRepo']['url']
    os.makedirs('inventory/targets', exist_ok=True)
    yaml_dump(_full_target(cluster, cfg.get_components().keys(),
                           catalog), 'inventory/targets/cluster.yml')

    return 'cluster'
