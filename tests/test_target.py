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
    all_classes = ([f"defaults.{cn}" for cn in components] +
                   ['global.common',
                       f"global.{facts['distribution']}",
                       f"global.{facts['cloud']}",
                       f"{cluster_obj['tenant']}.{cluster_obj['id']}",
                    ])
    assert len(target['classes']) == len(
        all_classes), "rendered target includes different amount of classes"
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
