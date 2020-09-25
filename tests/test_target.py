"""
Unit-tests for target generation
"""

import os
import click
import pytest

from textwrap import dedent

from commodore import cluster


@pytest.fixture
def data():
    """
    Setup test data
    """

    data = {
        'cluster': {
            'id': 'mycluster',
            'tenant': 'mytenant',
            'facts': {
                'distribution': 'rancher',
                'cloud': 'cloudscale',
            },
        },
        'components': [],
        'catalog': 'ssh://git@git.example.com/cluster-catalogs/mycluster',
    }
    return data


def test_render_target(data):
    target = cluster._full_target(data['cluster'], data['components'], data['catalog'])
    facts = data['cluster']['facts']
    all_classes = [f"defaults.{cn}" for cn in data['components']] + [
        'global.common',
        f"global.distribution.{facts['distribution']}",
        f"global.cloud.{facts['cloud']}",
        f"{data['cluster']['tenant']}.{data['cluster']['id']}"]
    assert target != ""
    assert len(target['classes']) == len(all_classes), \
        "rendered target includes different amount of classes"
    for i in range(len(all_classes)):
        assert target['classes'][i] == all_classes[i]
    assert target['parameters']['target_name'] == 'cluster'


def test_optional_fact_region(data):
    data['cluster']['facts']['region'] = 'rma1'
    target = cluster._full_target(data['cluster'], data['components'], data['catalog'])
    facts = data['cluster']['facts']
    assert f"global.cloud.{facts['cloud']}.{facts['region']}" in target['classes']


def test_optional_fact_region_empty(data):
    data['cluster']['facts']['region'] = ''
    target = cluster._full_target(data['cluster'], data['components'], data['catalog'])
    facts = data['cluster']['facts']
    assert f"global.cloud.{facts['cloud']}.{facts['region']}" not in target['classes']


def test_optional_fact_lieutenant_instance(data):
    data['cluster']['facts']['lieutenant-instance'] = 'lieutenant-dev'
    target = cluster._full_target(data['cluster'], data['components'], data['catalog'])
    facts = data['cluster']['facts']
    assert f"global.lieutenant-instance.{facts['lieutenant-instance']}" in target['classes']


def test_missing_facts(data):
    data['cluster']['facts'].pop('cloud')
    with pytest.raises(click.ClickException):
        cluster._full_target(data['cluster'], data['components'], data['catalog'])


def test_empty_facts(data):
    data['cluster']['facts']['cloud'] = ''
    with pytest.raises(click.ClickException):
        cluster._full_target(data['cluster'], data['components'], data['catalog'])


def test_reconstruct_api_response(tmp_path):
    os.chdir(tmp_path)
    targetyml = tmp_path / 'cluster.yml'
    with open(targetyml, 'w') as file:
        file.write(dedent('''
            classes:
            - defaults.argocd
            - global.common
            - global.distribution.k3d
            - global.cloud.localdev
            - t-delicate-pine-3938.c-twilight-water-9032
            parameters:
              cluster:
                catalog_url: ssh://git@git.vshn.net/syn-dev/cluster-catalogs/srueg-k3d-int.git
                name: c-twilight-water-9032
                tenant: t-delicate-pine-3938
              facts:
                cloud: localdev
                distribution: k3d
                region: north
              target_name: cluster'''))

    api_response = cluster.reconstruct_api_response(targetyml)
    assert api_response['id'] == 'c-twilight-water-9032'
    assert api_response['tenant'] == 't-delicate-pine-3938'
    assert api_response['facts']['distribution'] == 'k3d'
    assert api_response['facts']['region'] == 'north'


def test_reconstruct_api_response_missing_fact(tmp_path):
    os.chdir(tmp_path)
    targetyml = tmp_path / 'cluster.yml'
    with open(targetyml, 'w') as file:
        file.write(dedent('''
            classes: []
            parameters: {}'''))

    with pytest.raises(KeyError):
        cluster.reconstruct_api_response(targetyml)
