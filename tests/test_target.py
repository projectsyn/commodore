"""
Unit-tests for target generation
"""

import os
import click
import pytest

from pathlib import Path as P
from textwrap import dedent

from commodore import cluster


@pytest.fixture
def data():
    """
    Setup test data
    """

    return {
        'id': 'mycluster',
        'tenant': 'mytenant',
        'facts': {
            'distribution': 'rancher',
            'cloud': 'cloudscale',
        },
        'gitRepo': {
            'url': 'ssh://git@git.example.com/cluster-catalogs/mycluster',
        },
    }


def test_render_target(tmp_path):
    os.chdir(tmp_path)
    bar_defaults = P('inventory/classes/defaults/bar.yml')
    os.makedirs(bar_defaults.parent, exist_ok=True)
    bar_defaults.touch()
    target = cluster.render_target('foo', ['bar', 'baz'])
    classes = [
        'params.foo',
        'defaults.bar',
        'global.commodore',
    ]
    assert target != ""
    print(target)
    assert len(target['classes']) == len(classes), \
        "rendered target includes different amount of classes"
    for i in range(len(classes)):
        assert target['classes'][i] == classes[i]


def test_render_params(data):
    params = cluster.render_params(data, 'foo')
    assert params['parameters']['target_name'] == 'foo'
    assert params['parameters']['cluster']['name'] == 'mycluster'
    assert params['parameters']['cluster']['catalog_url'] == 'ssh://git@git.example.com/cluster-catalogs/mycluster'
    assert params['parameters']['cluster']['tenant'] == 'mytenant'
    assert params['parameters']['cluster']['dist'] == 'rancher'
    assert params['parameters']['facts'] == data['facts']
    assert params['parameters']['cloud']['provider'] == 'cloudscale'
    assert params['parameters']['customer']['name'] == 'mytenant'


def test_missing_facts(data):
    data['facts'].pop('cloud')
    with pytest.raises(click.ClickException):
        cluster.render_params(data, 'foo')


def test_empty_facts(data):
    data['facts']['cloud'] = ''
    with pytest.raises(click.ClickException):
        cluster.render_params(data, 'foo')


def test_reconstruct_api_response(tmp_path):
    os.chdir(tmp_path)
    file = cluster.params_file('foo')
    os.makedirs(file.parent, exist_ok=True)
    with open(file, 'w') as f:
        f.write(dedent('''
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

    api_response = cluster.reconstruct_api_response('foo')
    assert api_response['id'] == 'c-twilight-water-9032'
    assert api_response['tenant'] == 't-delicate-pine-3938'
    assert api_response['facts']['distribution'] == 'k3d'
    assert api_response['facts']['region'] == 'north'


def test_reconstruct_api_response_missing_fact(tmp_path):
    os.chdir(tmp_path)
    file = cluster.params_file('foo')
    os.makedirs(file.parent, exist_ok=True)
    with open(file, 'w') as f:
        f.write(dedent('''
            classes: []
            parameters: {}'''))

    with pytest.raises(KeyError):
        cluster.reconstruct_api_response('foo')
