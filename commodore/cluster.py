import os

from pathlib import Path as P

from typing import Iterable

import click

from .helpers import (
    lieutenant_query,
    yaml_dump,
    yaml_load,
)

from .config import Config


def fetch_cluster(cfg, clusterid):
    cluster = lieutenant_query(cfg.api_url, cfg.api_token, 'clusters', clusterid)
    # TODO: move Commodore global defaults repo name into Lieutenant
    # API/cluster facts
    cluster['base_config'] = 'commodore-defaults'
    return cluster


def reconstruct_api_response(target):
    file = params_file(target)
    if not file.is_file():
        raise click.ClickException(f"params file for target {target} does not exist")

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


def render_target(target: str, components: Iterable[str]):
    classes = [f"params.{target}"]

    for component in components:
        defaults_file = P('inventory', 'classes', 'defaults') / f"{component}.yml"
        if defaults_file.is_file():
            classes.append(f"defaults.{component}")

    classes.append('global.commodore')

    return {
        'classes': classes,
    }


def target_file(target: str):
    return P('inventory', 'targets') / f"{target}.yml"


def update_target(cfg: Config, target):
    click.secho('Updating Kapitan target...', bold=True)
    file = target_file(target)
    os.makedirs(file.parent, exist_ok=True)
    yaml_dump(render_target(target, cfg.get_components().keys()), file)


def render_params(cluster, target: str):
    facts = cluster['facts']
    for fact in ['distribution', 'cloud']:
        if fact not in facts or not facts[fact]:
            raise click.ClickException(f"Required fact '{fact}' not set")

    data = {
        'parameters': {
            'target_name': target,
            'cluster': {
                'name': cluster['id'],
                'catalog_url': cluster['gitRepo']['url'],
                'tenant': cluster['tenant'],
                # TODO Remove dist after deprecation phase.
                'dist': facts['distribution'],
            },
            'facts': facts,
            # TODO Remove the cloud and customer parameters after deprecation phase.
            'cloud': {
                'provider': facts['cloud'],
            },
            'customer': {
                'name': cluster['tenant'],
            },
        },
    }

    # TODO Remove after deprecation phase.
    if 'region' in facts:
        data['parameters']['cloud']['region'] = facts['region']

    return data


def params_file(target: str):
    return P('inventory', 'classes', 'params') / f"{target}.yml"


def update_params(cluster, target):
    click.secho('Updating cluster parameters...', bold=True)
    file = params_file(target)
    os.makedirs(file.parent, exist_ok=True)
    yaml_dump(render_params(cluster, target), file)
