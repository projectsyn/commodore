"""
Unit-tests for target generation
"""

import os
import click
import pytest

from pathlib import Path as P
from textwrap import dedent

from commodore import cluster, __kustomize_wrapper__
from commodore.inventory import Inventory
from commodore.config import Config


class MockComponent:
    def __init__(self, base_dir: P, name: str):
        self.name = name
        self._target_directory = base_dir / name

    @property
    def target_directory(self):
        return self._target_directory


def cluster_from_data(apidata) -> cluster.Cluster:
    return cluster.Cluster(apidata["cluster"], apidata["tenant"])


def _setup_working_dir(inv: Inventory, components):
    for cls in components:
        defaults = inv.defaults_file(cls)
        os.makedirs(defaults.parent, exist_ok=True)
        defaults.touch()
        component = inv.component_file(cls)
        os.makedirs(component.parent, exist_ok=True)
        component.touch()


def test_render_bootstrap_target(tmp_path: P):
    components = ["foo", "bar"]
    inv = Inventory(work_dir=tmp_path)
    _setup_working_dir(inv, components)

    components = {
        "foo": MockComponent(tmp_path, "foo"),
        "bar": MockComponent(tmp_path, "bar"),
        "baz": MockComponent(tmp_path, "baz"),
    }

    target = cluster.render_target(inv, "cluster", components)

    classes = [
        "params.cluster",
        "defaults.foo",
        "defaults.bar",
        "global.commodore",
    ]
    assert target != ""
    assert len(target["classes"]) == len(
        classes
    ), "rendered target includes different amount of classes"
    for i in range(len(classes)):
        assert target["classes"][i] == classes[i]
    assert target["parameters"]["_instance"] == "cluster"
    assert "_base_directory" not in target["parameters"]
    assert "_kustomize_wrapper" not in target["parameters"]


def test_render_target(tmp_path: P):
    components = ["foo", "bar"]
    inv = Inventory(work_dir=tmp_path)
    _setup_working_dir(inv, components)

    components = {
        "foo": MockComponent(tmp_path, "foo"),
        "bar": MockComponent(tmp_path, "bar"),
        "baz": MockComponent(tmp_path, "baz"),
    }

    target = cluster.render_target(inv, "foo", components)

    classes = [
        "params.cluster",
        "defaults.foo",
        "defaults.bar",
        "global.commodore",
        "components.foo",
    ]
    assert target != ""
    assert len(target["classes"]) == len(
        classes
    ), "rendered target includes different amount of classes"
    for i in range(len(classes)):
        assert target["classes"][i] == classes[i]
    assert target["parameters"]["kapitan"]["vars"]["target"] == "foo"
    assert target["parameters"]["_instance"] == "foo"
    assert target["parameters"]["_base_directory"] == str(tmp_path / "foo")
    assert target["parameters"]["_kustomize_wrapper"] == str(__kustomize_wrapper__)


def test_render_aliased_target(tmp_path: P):
    components = ["foo", "bar"]
    inv = Inventory(work_dir=tmp_path)
    _setup_working_dir(inv, components)

    components = {
        "foo": MockComponent(tmp_path, "foo"),
        "bar": MockComponent(tmp_path, "bar"),
        "baz": MockComponent(tmp_path, "baz"),
    }

    target = cluster.render_target(inv, "fooer", components, component="foo")

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
    assert target["parameters"]["kapitan"]["vars"]["target"] == "fooer"
    assert target["parameters"]["foo"] == "${fooer}"
    assert target["parameters"]["_instance"] == "fooer"
    assert target["parameters"]["_base_directory"] == str(tmp_path / "foo")


def test_render_aliased_target_with_dash(tmp_path: P):
    components = ["foo-comp", "bar"]
    inv = Inventory(work_dir=tmp_path)
    _setup_working_dir(inv, components)

    components = {
        "foo-comp": MockComponent(tmp_path, "foo-comp"),
        "bar": MockComponent(tmp_path, "bar"),
        "baz": MockComponent(tmp_path, "baz"),
    }

    target = cluster.render_target(inv, "foo-1", components, component="foo-comp")

    classes = [
        "params.cluster",
        "defaults.foo-comp",
        "defaults.bar",
        "global.commodore",
        "components.foo-comp",
    ]
    assert target != ""
    print(target)
    assert len(target["classes"]) == len(
        classes
    ), "rendered target includes different amount of classes"
    for i in range(len(classes)):
        assert target["classes"][i] == classes[i]
    assert target["parameters"]["kapitan"]["vars"]["target"] == "foo-1"
    assert target["parameters"]["foo_comp"] == "${foo_1}"
    assert target["parameters"]["_instance"] == "foo-1"
    assert target["parameters"]["_base_directory"] == str(tmp_path / "foo-comp")


def test_render_params(api_data, tmp_path: P):
    cfg = Config(work_dir=tmp_path)
    target = cfg.inventory.bootstrap_target
    params = cluster.render_params(cfg.inventory, cluster_from_data(api_data))

    assert "parameters" in params

    params = params["parameters"]
    assert "cluster" in params

    assert "name" in params["cluster"]
    assert params["cluster"]["name"] == "c-bar"

    assert target in params
    target_params = params[target]

    assert "name" in target_params
    assert target_params["name"] == "c-bar"
    assert "display_name" in target_params
    assert target_params["display_name"] == "Foo Inc. Bar Cluster"
    assert "catalog_url" in target_params
    assert (
        target_params["catalog_url"]
        == "ssh://git@git.example.com/cluster-catalogs/mycluster"
    )
    assert "tenant" in target_params
    assert target_params["tenant"] == "t-foo"
    assert "tenant_display_name" in target_params
    assert target_params["tenant_display_name"] == "Foo Inc."

    assert "facts" in params
    assert params["facts"] == api_data["cluster"]["facts"]

    assert "dynamic_facts" in params
    dyn_facts = params["dynamic_facts"]
    assert "kubernetes_version" in dyn_facts
    k8s_ver = dyn_facts["kubernetes_version"]
    assert "major" in k8s_ver
    assert "minor" in k8s_ver
    assert "gitVersion" in k8s_ver
    assert "1" == k8s_ver["major"]
    assert "21" == k8s_ver["minor"]
    assert "v1.21.3" == k8s_ver["gitVersion"]


def test_missing_facts(api_data, tmp_path: P):
    api_data["cluster"]["facts"].pop("cloud")
    cfg = Config(work_dir=tmp_path)
    with pytest.raises(click.ClickException):
        cluster.render_params(cfg.inventory, cluster_from_data(api_data))


def test_empty_facts(api_data, tmp_path: P):
    api_data["cluster"]["facts"]["cloud"] = ""
    cfg = Config(work_dir=tmp_path)
    with pytest.raises(click.ClickException):
        cluster.render_params(cfg.inventory, cluster_from_data(api_data))


def test_read_cluster_and_tenant(tmp_path):
    cfg = Config(work_dir=tmp_path)
    file = cfg.inventory.params_file
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

    cluster_id, tenant_id = cluster.read_cluster_and_tenant(cfg.inventory)
    assert cluster_id == "c-twilight-water-9032"
    assert tenant_id == "t-delicate-pine-3938"


def test_read_cluster_and_tenant_missing_fact(tmp_path):
    inv = Inventory(work_dir=tmp_path)
    file = inv.params_file
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
        cluster.read_cluster_and_tenant(inv)
