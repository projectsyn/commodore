"""
Unit-tests for target generation
"""

import os
import click
import pytest

from textwrap import dedent

from commodore import cluster
from commodore.inventory import Inventory


@pytest.fixture
def data():
    """
    Setup test data
    """

    return {
        "id": "mycluster",
        "tenant": "mytenant",
        "facts": {
            "distribution": "rancher",
            "cloud": "cloudscale",
        },
        "gitRepo": {
            "url": "ssh://git@git.example.com/cluster-catalogs/mycluster",
        },
    }


def cluster_from_data(data) -> cluster.Cluster:
    return cluster.Cluster(None, data, {"id": data["tenant"]})


def test_render_target(tmp_path):
    os.chdir(tmp_path)
    inv = Inventory()
    for cls in ["foo", "bar"]:
        defaults = inv.defaults_file(cls)
        os.makedirs(defaults.parent, exist_ok=True)
        defaults.touch()
        component = inv.component_file(cls)
        os.makedirs(component.parent, exist_ok=True)
        component.touch()
    target = cluster.render_target(inv, "foo", ["foo", "bar", "baz"])
    classes = [
        "params.cluster",
        "defaults.foo",
        "defaults.bar",
        "global.commodore",
        "components.foo",
    ]
    assert target != ""
    print(target)
    assert len(target["classes"]) == len(
        classes
    ), "rendered target includes different amount of classes"
    for i in range(len(classes)):
        assert target["classes"][i] == classes[i]
    assert target["parameters"]["kapitan"]["vars"]["target"] == "foo"


def test_render_params(data):
    params = cluster.render_params(cluster_from_data(data))
    assert params["parameters"]["cluster"]["name"] == "mycluster"
    assert params["parameters"][cluster.BOOTSTRAP_TARGET]["name"] == "mycluster"
    assert (
        params["parameters"][cluster.BOOTSTRAP_TARGET]["catalog_url"]
        == "ssh://git@git.example.com/cluster-catalogs/mycluster"
    )
    assert params["parameters"][cluster.BOOTSTRAP_TARGET]["tenant"] == "mytenant"
    assert params["parameters"][cluster.BOOTSTRAP_TARGET]["dist"] == "rancher"
    assert params["parameters"]["facts"] == data["facts"]
    assert params["parameters"]["cloud"]["provider"] == "cloudscale"
    assert params["parameters"]["customer"]["name"] == "mytenant"


def test_missing_facts(data):
    data["facts"].pop("cloud")
    with pytest.raises(click.ClickException):
        cluster.render_params(cluster_from_data(data))


def test_empty_facts(data):
    data["facts"]["cloud"] = ""
    with pytest.raises(click.ClickException):
        cluster.render_params(cluster_from_data(data))


def test_read_cluster_and_tenant(tmp_path):
    os.chdir(tmp_path)
    file = cluster.params_file()
    os.makedirs(file.parent, exist_ok=True)
    with open(file, "w") as f:
        f.write(
            dedent(
                """
            parameters:
              cluster:
                name: c-twilight-water-9032
                tenant: t-delicate-pine-3938"""
            )
        )

    cluster_id, tenant_id = cluster.read_cluster_and_tenant()
    assert cluster_id == "c-twilight-water-9032"
    assert tenant_id == "t-delicate-pine-3938"


def test_read_cluster_and_tenant_missing_fact(tmp_path):
    os.chdir(tmp_path)
    file = cluster.params_file()
    os.makedirs(file.parent, exist_ok=True)
    with open(file, "w") as f:
        f.write(
            dedent(
                """
            classes: []
            parameters: {}"""
            )
        )

    with pytest.raises(KeyError):
        cluster.read_cluster_and_tenant()
