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


def reconstruct_api_response(file):
    data = yaml_load(file)
    parameters = data['parameters']
    response = {
        'id': parameters['cluster']['name'],
        'facts': parameters['facts'],
        'gitRepo': {
            'url': parameters['cluster']['catalog_url'],
        },
        'tenant': parameters['cluster']['tenant'],
    }

    return response


def _full_target(cluster, components, catalog):
    cluster_facts = cluster['facts']
    for required_fact in ['distribution', 'cloud']:
        if required_fact not in cluster_facts or not cluster_facts[required_fact]:
            raise click.ClickException(f"Required fact '{required_fact}' not set")

    cluster_distro = cluster_facts['distribution']
    cloud_provider = cluster_facts['cloud']
    cluster_id = cluster['id']
    tenant = cluster['tenant']
    component_defaults = [f"defaults.{cn}" for cn in components if
                          (P('inventory/classes/defaults') / f"{cn}.yml").is_file()]
    global_defaults = ['global.common',
                       f"global.distribution.{cluster_distro}",
                       f"global.cloud.{cloud_provider}"]
    if 'region' in cluster_facts and cluster_facts['region']:
        global_defaults.append(f"global.cloud.{cloud_provider}.{cluster_facts['region']}")

    if 'lieutenant-instance' in cluster_facts and cluster_facts['lieutenant-instance']:
        global_defaults.append(
            f"global.lieutenant-instance.{cluster_facts['lieutenant-instance']}")
    global_defaults.append(f"{tenant}.{cluster_id}")
    commodore_facts = {
        'target_name': 'cluster',
        'cluster': {
            'name': cluster_id,
            'catalog_url': catalog,
            'tenant': tenant,
            # TODO Remove dist after deprecation phase.
            'dist': cluster_distro,
        },
        # TODO Remove the facts below after deprecation phase.
        'cloud': {
            'provider': cloud_provider,
        },
        'customer': {
            'name': tenant,
        },
    }
    # TODO Remove after deprecation phase.
    if 'region' in cluster_facts:
        commodore_facts['cloud']['region'] = cluster_facts['region']
    target = {
        'classes': component_defaults + global_defaults,
        'parameters': {
            **commodore_facts,
            **{
                'facts': cluster_facts,
            },
        },
    }
    return target


def update_target(cfg, cluster):
    click.secho('Updating Kapitan target...', bold=True)
    catalog = cluster['gitRepo']['url']
    os.makedirs('inventory/targets', exist_ok=True)
    yaml_dump(_full_target(cluster, cfg.get_components().keys(),
                           catalog), 'inventory/targets/cluster.yml')

    return 'cluster'
