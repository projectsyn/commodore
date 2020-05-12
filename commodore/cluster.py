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
        'id': target_data['cluster']['name'],
        'facts': {
            'cloud': target_data['cloud']['region'],
            'distribution': target_data['cluster']['dist'],
            'region': target_data['cloud']['region'],
        },
        'gitRepo': {
            'url': target_data['cluster']['catalog_url'],
        },
        'tenant': target_data['customer']['name'],
    }


def _full_target(cluster, components, catalog):
    cluster_facts = cluster['facts']
    for required_fact in ['distribution', 'cloud']:
        if required_fact not in cluster_facts:
            raise click.ClickException(f"Required fact '{required_fact}' not set")

    cluster_distro = cluster_facts['distribution']
    cloud_provider = cluster_facts['cloud']
    cluster_id = cluster['id']
    customer = cluster['tenant']
    component_defaults = [f"defaults.{cn}" for cn in components if
                          (P('inventory/classes/defaults') / f"{cn}.yml").is_file()]
    global_defaults = ['global.common', f"global.{cluster_distro}", f"global.{cloud_provider}"]
    if 'region' in cluster_facts:
        global_defaults.append(f"global.{cloud_provider}.{cluster_facts['region']}")
    global_defaults.append(f"{customer}.{cluster_id}")
    target = {
        'classes': component_defaults + global_defaults,
        'parameters': {
            'target_name': 'cluster',
            'cluster': {
                'name': f"{cluster_id}",
                'dist': f"{cluster_distro}",
                'catalog_url': f"{catalog}",
            },
            'cloud': {
                'provider': f"{cloud_provider}",
            },
            'customer': {
                'name': f"{customer}"
            },
        }
    }
    if 'region' in cluster_facts:
        target['parameters']['cloud']['region'] = cluster_facts['region']
    return target


def update_target(cfg, cluster):
    click.secho('Updating Kapitan target...', bold=True)
    catalog = cluster['gitRepo']['url']
    os.makedirs('inventory/targets', exist_ok=True)
    yaml_dump(_full_target(cluster, cfg.get_components().keys(),
                           catalog), 'inventory/targets/cluster.yml')

    return 'cluster'
