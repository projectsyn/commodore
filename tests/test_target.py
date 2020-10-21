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


def test_render_target(tmp_path):
    os.chdir(tmp_path)
    classdir = P("inventory/classes")
    for cls in ["foo", "bar"]:
        defaults = classdir / "defaults" / f"{cls}.yml"
        os.makedirs(defaults.parent, exist_ok=True)
        defaults.touch()
        component = classdir / "components" / f"{cls}.yml"
        os.makedirs(component.parent, exist_ok=True)
        component.touch()
    target = cluster.render_target("foo", ["foo", "bar", "baz"])
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
    params = cluster.render_params(data)
    assert params["parameters"]["cluster"]["name"] == "mycluster"
    assert (
        params["parameters"]["cluster"]["catalog_url"]
        == "ssh://git@git.example.com/cluster-catalogs/mycluster"
    )
    assert params["parameters"]["cluster"]["tenant"] == "mytenant"
    assert params["parameters"]["cluster"]["dist"] == "rancher"
    assert params["parameters"]["facts"] == data["facts"]
    assert params["parameters"]["cloud"]["provider"] == "cloudscale"
    assert params["parameters"]["customer"]["name"] == "mytenant"


def test_missing_facts(data):
    data["facts"].pop("cloud")
    with pytest.raises(click.ClickException):
        cluster.render_params(data)


def test_empty_facts(data):
    data["facts"]["cloud"] = ""
    with pytest.raises(click.ClickException):
        cluster.render_params(data)


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
