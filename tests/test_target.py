"""
Unit-tests for target generation
"""

import click
import pytest
import commodore.cluster as cluster


cluster_obj = {
    'id': 'mycluster',
    'tenant': 'mytenant',
    'facts': {
        'distribution': 'rancher',
        'cloud': 'cloudscale',
    }
}
components = ['test-component']
catalog = 'ssh://git@git.example.com/cluster-catalogs/mycluster'


def test_render_target():
    target = cluster._full_target(cluster_obj, components, catalog)
    facts = cluster_obj['facts']
    assert target != ""
    all_classes = [f"defaults.{cn}" for cn in components] + \
        ['global.common',
         f"global.{facts['distribution']}",
         f"global.{facts['cloud']}",
         f"{cluster_obj['tenant']}.{cluster_obj['id']}"]
    assert len(target['classes']) == len(all_classes), \
        "rendered target includes different amount of classes"
    # Test order of included classes
    for i in range(len(all_classes)):
        assert target['classes'][i] == all_classes[i]
    assert target['parameters']['target_name'] == 'cluster'


def test_optional_facts():
    cluster_obj['facts']['region'] = 'rma1'
    target = cluster._full_target(cluster_obj, components, catalog)
    facts = cluster_obj['facts']
    assert f"global.{facts['cloud']}.{facts['region']}" in target['classes']


def test_missing_facts():
    cl = {
        'id': 'mycluster',
        'tenant': 'mytenant',
        'facts': {
            'distribution': 'rancher',
        }
    }
    with pytest.raises(click.ClickException):
        cluster._full_target(cl, components, catalog)


def test_reconstruct_api_response(tmp_path):
    targetyml = tmp_path / 'cluster.yml'
    with open(targetyml, 'w') as file:
        file.write('''classes:
- defaults.argocd
- global.common
- global.k3d
- global.localdev
- t-delicate-pine-3938.c-twilight-water-9032
parameters:
  cloud:
    provider: localdev
    region: north
  cluster:
    catalog_url: ssh://git@git.vshn.net/syn-dev/cluster-catalogs/srueg-k3d-int.git
    dist: k3d
    name: c-twilight-water-9032
  customer:
    name: t-delicate-pine-3938
  target_name: cluster ''')

    api_response = cluster.reconstruct_api_response(targetyml)
    assert api_response['id'] == 'c-twilight-water-9032'
    assert api_response['tenant'] == 't-delicate-pine-3938'
    assert api_response['facts']['distribution'] == 'k3d'
    assert api_response['facts']['region'] == 'north'


def test_reconstruct_api_response_no_region(tmp_path):
    targetyml = tmp_path / 'cluster.yml'
    with open(targetyml, 'w') as file:
        file.write('''classes:
parameters:
  cloud:
    provider: localdev
  cluster:
    catalog_url: ssh://git@git.vshn.net/syn-dev/cluster-catalogs/srueg-k3d-int.git
    dist: k3d
    name: c-twilight-water-9032
  customer:
    name: t-delicate-pine-3938
  target_name: cluster ''')

    api_response = cluster.reconstruct_api_response(targetyml)
    assert 'region' not in api_response['facts']


def test_reconstruct_api_response_missing_fact(tmp_path):
    targetyml = tmp_path / 'cluster.yml'
    with open(targetyml, 'w') as file:
        file.write('''classes:
parameters:
  cloud:
    region: north
  cluster:
    catalog_url: ssh://git@git.vshn.net/syn-dev/cluster-catalogs/srueg-k3d-int.git
    dist: k3d
    name: c-twilight-water-9032
  customer:
    name: t-delicate-pine-3938
  target_name: cluster ''')

    with pytest.raises(KeyError):
        cluster.reconstruct_api_response(targetyml)
