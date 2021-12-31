"""
Unit-tests for dependency management
"""

import os
import click
import git
import pytest
import json
from unittest.mock import patch
from pathlib import Path

from commodore import dependency_mgmt
from commodore.config import Config
from commodore.component import Component
from commodore.helpers import relsymlink
from commodore.inventory import Inventory

from bench_component import setup_components_upstream


@pytest.fixture
def data(tmp_path):
    """
    Setup test data
    """

    return Config(
        tmp_path,
        api_url="https://syn.example.com",
        api_token="token",
    )


def test_symlink(tmp_path: Path):
    test_file = tmp_path / "test1"
    relsymlink(test_file, tmp_path)
    assert test_file.is_symlink()


def test_override_symlink(tmp_path: Path):
    test_file = tmp_path / "test2"
    test_file.touch()
    assert not test_file.is_symlink()
    relsymlink(test_file, tmp_path)
    assert test_file.is_symlink()


def test_create_component_symlinks_fails(data: Config, tmp_path: Path):
    component = Component("my-component", work_dir=tmp_path)
    with pytest.raises(FileNotFoundError):
        dependency_mgmt.create_component_symlinks(data, component)


def test_create_component_symlinks(capsys, data: Config, tmp_path):
    component = Component("my-component", work_dir=tmp_path)
    component.class_file.parent.mkdir(parents=True, exist_ok=True)
    with open(component.class_file, "w") as f:
        f.writelines(["class"])
    with open(component.defaults_file, "w") as f:
        f.writelines(["default"])
    lib_dir = component.target_directory / "lib"
    lib_dir.mkdir(parents=True, exist_ok=True)
    lib_file = lib_dir / "my-component.libjsonnet"
    with open(lib_file, "w") as f:
        f.writelines(["lib"])

    inv = Inventory(work_dir=tmp_path)
    inv.ensure_dirs()

    dependency_mgmt.create_component_symlinks(data, component)

    for path, marker in [
        (
            tmp_path / "inventory" / "classes" / "components" / f"{component.name}.yml",
            "class",
        ),
        (
            tmp_path / "inventory" / "classes" / "defaults" / f"{component.name}.yml",
            "default",
        ),
        (tmp_path / "dependencies" / "lib" / "my-component.libjsonnet", "lib"),
    ]:
        # Ensure symlinks exist
        assert path.is_symlink()
        # Ensure symlink targets exist
        assert path.resolve().is_file()
        # Ensure symlinked file contains correct marker content
        with open(path) as f:
            fcontents = f.readlines()
            assert fcontents[0] == marker
    assert capsys.readouterr().out == ""


def _setup_mock_inventory(patch_inventory, aliases={}):
    components = {
        "test-component": {
            "url": "https://github.com/projectsyn/component-test-component.git",
            "version": "master",
        },
        "other-component": {
            "url": "ssh://git@git.acme.com/some/component.git",
        },
        "third-component": {
            "url": "https://github.com/projectsyn/component-third-component.git",
            "version": "feat/test",
        },
    }
    assert set(aliases.keys()) <= set(components.keys())
    applications = list(components.keys())
    for c, a in aliases.items():
        applications.append(f"{c} as {a}")
    params = {"components": components}
    nodes = {
        a: {"applications": sorted(applications), "parameters": params}
        for a in applications
    }
    nodes["cluster"] = {"applications": sorted(applications), "parameters": params}
    mock_inventory = {
        "applications": {a: applications for a in applications},
        "nodes": nodes,
    }

    def inv(inventory_dir, key="nodes"):
        return mock_inventory[key]

    patch_inventory.side_effect = inv

    return mock_inventory["nodes"]["cluster"]["parameters"]["components"]


@patch.object(dependency_mgmt, "kapitan_inventory")
def test_read_components(patch_inventory, data: Config):
    components = _setup_mock_inventory(patch_inventory)
    component_urls, component_versions = dependency_mgmt._read_components(
        data, ["test-component"]
    )

    # check that exactly 'test-component' is discovered
    assert {"test-component"} == set(component_urls.keys())
    assert components["test-component"]["url"] == component_urls["test-component"]
    assert (
        components["test-component"]["version"] == component_versions["test-component"]
    )


@patch.object(dependency_mgmt, "kapitan_inventory")
def test_read_components_multiple(patch_inventory, data: Config):
    components = _setup_mock_inventory(patch_inventory)
    component_urls, component_versions = dependency_mgmt._read_components(
        data, components.keys()
    )
    # check that exactly 'test-component' is discovered
    assert set(components.keys()) == set(component_urls.keys())
    assert set(components.keys()) == set(component_versions.keys())
    assert all(components[cn]["url"] == component_urls[cn] for cn in components.keys())
    assert all(
        components[cn].get("version", None) == component_versions[cn]
        for cn in components.keys()
    )


@patch("commodore.dependency_mgmt.kapitan_inventory")
def test_read_components_deprecation(
    patch_inventory, data: Config, tmp_path: Path, capsys
):
    components = _setup_mock_inventory(patch_inventory)

    _ = dependency_mgmt._read_components(data, components.keys())

    data.print_deprecation_notices()
    captured = capsys.readouterr()

    # We split and join captured.out to revert the formatting done by
    # print_deprecation_notices().
    assert (
        "Component other-component doesn't have a version specified. "
        + "See https://syn.tools/commodore/reference/deprecation-notices.html"
        + "#_components_without_versions for more details."
    ) in " ".join(captured.out.split())


@pytest.mark.parametrize(
    "components,ckeys,exctext",
    [
        ({}, [], "Component list ('parameters.components') missing"),
        (
            {"components": {"a": {"url": "a_url"}}},
            ["b"],
            "Unknown component 'b'. Please add it to 'parameters.components'",
        ),
        (
            {"components": {"a": {"version": "a_version"}}},
            ["a"],
            "No url for component 'a' configured",
        ),
    ],
)
@patch("commodore.dependency_mgmt.kapitan_inventory")
def test_read_components_exc(
    patch_inventory,
    data: Config,
    tmp_path: Path,
    capsys,
    components,
    ckeys,
    exctext,
):
    patch_inventory.return_value = {
        data.inventory.bootstrap_target: {"parameters": components},
    }

    with pytest.raises(click.ClickException) as exc_info:
        _ = dependency_mgmt._read_components(data, ckeys)

    assert exc_info.value.args[0] == exctext


@patch.object(dependency_mgmt, "kapitan_inventory")
def test_discover_components(patch_inventory, data: Config):
    component_inv = _setup_mock_inventory(patch_inventory)

    components, aliases = dependency_mgmt._discover_components(data)
    assert components == sorted(component_inv.keys())
    assert sorted(aliases.keys()) == components
    assert all(k == v for k, v in aliases.items())


@patch.object(dependency_mgmt, "kapitan_inventory")
def test_discover_components_aliases(patch_inventory, data: Config):
    expected_aliases = {"other-component": "aliased"}
    component_inv = _setup_mock_inventory(patch_inventory, expected_aliases)

    components, aliases = dependency_mgmt._discover_components(data)
    assert components == sorted(component_inv.keys())
    assert set(components + list(expected_aliases.values())) == set(aliases.keys())
    assert set(aliases.values()) == set(components)
    assert aliases["aliased"] == "other-component"


@pytest.mark.parametrize(
    "components,expected",
    [
        ([], ""),
        (["a"], "'a'"),
        (["a", "b"], "'a' and 'b'"),
        # Verify that Oxford comma is used in lists with >= items
        (
            ["a", "b", "c"],
            "'a', 'b', and 'c'",
        ),
        (
            ["a", "b", "c", "d", "e"],
            "'a', 'b', 'c', 'd', and 'e'",
        ),
    ],
)
def test_format_component_list(components, expected):
    assert dependency_mgmt._format_component_list(components) == expected


@pytest.mark.parametrize(
    "expected_aliases,expected_exception_msg",
    [
        (
            {"other-component": "aliased", "third-component": "aliased"},
            "Duplicate component alias 'aliased': components "
            + "'other-component' and 'third-component' are aliased to 'aliased'",
        ),
        (
            {"other-component": "third-component", "third-component": "aliased"},
            "Component 'other-component' aliases existing component 'third-component'",
        ),
        (
            {
                "test-component": "third-component",
                "other-component": "third-component",
                "third-component": "aliased",
            },
            "Components 'other-component' and 'test-component' alias "
            + "existing component 'third-component'",
        ),
    ],
)
@patch.object(dependency_mgmt, "kapitan_inventory")
def test_discover_components_duplicate_aliases(
    patch_inventory, data: Config, expected_aliases, expected_exception_msg
):
    _setup_mock_inventory(patch_inventory, expected_aliases)

    with pytest.raises(KeyError) as e:
        dependency_mgmt._discover_components(data)

    assert e.value.args[0] == expected_exception_msg


@patch("commodore.dependency_mgmt._read_components")
@patch("commodore.dependency_mgmt._discover_components")
def test_fetch_components(patch_discover, patch_read, data: Config, tmp_path: Path):
    components = ["component-one", "component-two"]
    patch_discover.return_value = (components, {})
    patch_read.return_value = setup_components_upstream(tmp_path, components)

    dependency_mgmt.fetch_components(data)

    for component in components:
        assert component in data._components
        assert (
            tmp_path / "inventory" / "classes" / "components" / f"{component}.yml"
        ).is_symlink()
        assert (
            tmp_path / "inventory" / "classes" / "defaults" / f"{component}.yml"
        ).is_symlink()
        assert (tmp_path / "dependencies" / component).is_dir()


@patch("commodore.dependency_mgmt._read_components")
@patch("commodore.dependency_mgmt._discover_components")
def test_fetch_components_is_minimal(
    patch_discover, patch_urls, data: Config, tmp_path: Path
):
    components = ["component-one", "component-two"]
    other_components = ["component-three", "component-four"]
    patch_discover.return_value = (components, {})
    patch_urls.return_value = setup_components_upstream(tmp_path, components)
    # Setup upstreams for components which are not included
    extra_urls, extra_versions = setup_components_upstream(tmp_path, other_components)
    for cn in extra_urls.keys():
        patch_urls.return_value[0][cn] = extra_urls[cn]
        patch_urls.return_value[1][cn] = extra_versions[cn]

    dependency_mgmt.fetch_components(data)

    for component in components:
        assert component in data._components
        assert (
            tmp_path / "inventory" / "classes" / "components" / f"{component}.yml"
        ).is_symlink()
        assert (
            tmp_path / "inventory" / "classes" / "defaults" / f"{component}.yml"
        ).is_symlink()
        assert (tmp_path / "dependencies" / component).is_dir()

    for component in other_components:
        assert component not in data._components
        assert not (tmp_path / "dependencies" / component).exists()


def test_write_jsonnetfile(data: Config, tmp_path: Path):
    data.register_component(Component("test-component", work_dir=tmp_path))
    data.register_component(Component("test-component-2", work_dir=tmp_path))
    dirs = [
        "dependencies/test-component",
        "dependencies/test-component-2",
        "dependencies/lib",
    ]

    file = tmp_path / "jsonnetfile.json"

    dependency_mgmt.write_jsonnetfile(file, dependency_mgmt.jsonnet_dependencies(data))

    with open(file) as jf:
        jf_string = jf.read()
        assert jf_string[-1] == "\n"
        jf_contents = json.loads(jf_string)
        assert jf_contents["version"] == 1
        assert jf_contents["legacyImports"]
        deps = jf_contents["dependencies"]
        for dep in deps:
            assert dep["source"]["local"]["directory"] in dirs


def test_inject_essential_libraries(tmp_path: Path):
    file = tmp_path / "jsonnetfile.json"
    dependency_mgmt.write_jsonnetfile(file, [])

    dependency_mgmt.inject_essential_libraries(file)

    with open(file) as jf:
        jf_string = jf.read()
        assert jf_string[-1] == "\n"
        jf_contents = json.loads(jf_string)
        assert jf_contents["version"] == 1
        assert jf_contents["legacyImports"]
        deps = jf_contents["dependencies"]
        assert len(deps) == 1
        assert (
            deps[0]["source"]["git"]["remote"]
            == "https://github.com/bitnami-labs/kube-libsonnet"
        )
        assert deps[0]["version"] == "v1.14.6"


def test_clear_jsonnet_lock_file(tmp_path: Path):
    jsonnetfile = tmp_path / "jsonnetfile.json"
    jsonnet_lock = tmp_path / "jsonnetfile.lock.json"
    with open(jsonnetfile, "w") as jf:
        json.dump(
            {
                "version": 1,
                "dependencies": [
                    {
                        "source": {
                            "git": {
                                "remote": "https://github.com/brancz/kubernetes-grafana.git",
                                "subdir": "grafana",
                            }
                        },
                        "version": "master",
                    }
                ],
                "legacyImports": True,
            },
            jf,
        )
    with open(jsonnet_lock, "w") as jl:
        json.dump(
            {
                "version": 1,
                "dependencies": [
                    {
                        "source": {
                            "git": {
                                "remote": "https://github.com/brancz/kubernetes-grafana.git",
                                "subdir": "grafana",
                            }
                        },
                        "version": "57b4365eacda291b82e0d55ba7eec573a8198dda",
                        "sum": "92DWADwGjnCfpZaL7Q07C0GZayxBziGla/O03qWea34=",
                    }
                ],
                "legacyImports": True,
            },
            jl,
        )
    dependency_mgmt.fetch_jsonnet_libraries(tmp_path)

    assert jsonnet_lock.is_file()
    with open(jsonnet_lock, "r") as file:
        data = json.load(file)
        assert (
            data["dependencies"][0]["version"]
            != "57b4365eacda291b82e0d55ba7eec573a8198dda"
        )


def _setup_register_components(tmp_path: Path):
    inv = Inventory(tmp_path)
    inv.ensure_dirs()
    component_dirs = ["foo", "bar", "baz"]
    other_dirs = ["lib", "libs"]
    for directory in component_dirs + other_dirs:
        cpath = tmp_path / "dependencies" / directory
        os.makedirs(cpath, exist_ok=True)
        r = git.Repo.init(cpath)
        r.create_remote("origin", f"ssh://git@example.com/git/{directory}")

    return component_dirs, other_dirs


@patch("commodore.dependency_mgmt._discover_components")
def test_register_components(patch_discover, data: Config, tmp_path: Path):
    component_dirs, other_dirs = _setup_register_components(tmp_path)
    patch_discover.return_value = (component_dirs, {})

    dependency_mgmt.register_components(data)

    component_names = data.get_components().keys()
    for c in component_dirs:
        assert c in component_names
    for c in other_dirs:
        assert c not in component_names


@patch("commodore.dependency_mgmt._discover_components")
def test_register_components_and_aliases(patch_discover, data: Config, tmp_path: Path):
    component_dirs, other_dirs = _setup_register_components(tmp_path)
    alias_data = {"fooer": "foo"}
    patch_discover.return_value = (component_dirs, alias_data)

    dependency_mgmt.register_components(data)

    component_names = data.get_components().keys()
    for c in component_dirs:
        assert c in component_names
    for c in other_dirs:
        assert c not in component_names

    aliases = data.get_component_aliases()
    for alias, cn in alias_data.items():
        if cn in component_dirs:
            assert alias in aliases
            assert aliases[alias] == cn
        else:
            assert alias not in aliases


@patch("commodore.dependency_mgmt._discover_components")
def test_register_unknown_components(
    patch_discover, data: Config, tmp_path: Path, capsys
):
    component_dirs, other_dirs = _setup_register_components(tmp_path)
    unknown_components = ["qux", "quux"]
    component_dirs.extend(unknown_components)
    patch_discover.return_value = (component_dirs, {})

    dependency_mgmt.register_components(data)

    captured = capsys.readouterr()
    for cn in unknown_components:
        assert f"Skipping registration of component {cn}" in captured.out


@patch("commodore.dependency_mgmt._discover_components")
def test_register_dangling_aliases(
    patch_discover, data: Config, tmp_path: Path, capsys
):
    component_dirs, other_dirs = _setup_register_components(tmp_path)
    # add some dangling aliases
    alias_data = {"quxer": "qux", "quuxer": "quux"}
    # generate expected output
    should_miss = sorted(set(alias_data.keys()))
    # add an alias that should work
    alias_data["bazzer"] = "baz"

    patch_discover.return_value = (component_dirs, alias_data)

    dependency_mgmt.register_components(data)

    captured = capsys.readouterr()
    assert (
        f"Dropping alias(es) {should_miss} with missing component(s)." in captured.out
    )
