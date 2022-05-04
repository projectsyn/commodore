"""
Unit-tests for dependency management
"""
from __future__ import annotations

import os
import click
import git
import pytest
from collections.abc import Iterable
from unittest.mock import patch
from pathlib import Path

from commodore import dependency_mgmt
from commodore.config import Config
from commodore.component import Component
from commodore.inventory import Inventory


def setup_components_upstream(tmp_path: Path, components: Iterable[str]):
    # Prepare minimum component directories
    upstream = tmp_path / "upstream"
    component_urls = {}
    component_versions = {}
    for component in components:
        repo_path = upstream / component
        component_urls[component] = f"file://#{repo_path.resolve()}"
        component_versions[component] = None
        repo = git.Repo.init(repo_path)

        class_dir = repo_path / "class"
        class_dir.mkdir(parents=True, exist_ok=True)
        (class_dir / "defaults.yml").touch(exist_ok=True)
        (class_dir / f"{component}.yml").touch(exist_ok=True)

        repo.index.add(["class/defaults.yml", f"class/{component}.yml"])
        repo.index.commit("component defaults")

    return component_urls, component_versions


def test_create_component_symlinks_fails(config: Config, tmp_path: Path):
    component = Component("my-component", work_dir=tmp_path)
    with pytest.raises(click.ClickException) as e:
        dependency_mgmt.create_component_symlinks(config, component)

    assert "Source does not exist" in str(e.value)


def setup_mock_component(tmp_path: Path, name="my-component") -> Component:
    component = Component(name, work_dir=tmp_path)
    component.class_file.parent.mkdir(parents=True, exist_ok=True)
    with open(component.class_file, "w") as f:
        f.writelines(["class"])
    with open(component.defaults_file, "w") as f:
        f.writelines(["default"])
    lib_dir = component.target_directory / "lib"
    lib_dir.mkdir(parents=True, exist_ok=True)
    lib_file = lib_dir / f"{component.name}.libjsonnet"
    with open(lib_file, "w") as f:
        f.writelines(["lib"])

    return component


def test_create_component_symlinks(capsys, config: Config, tmp_path):
    component = setup_mock_component(tmp_path)
    inv = Inventory(work_dir=tmp_path)
    inv.ensure_dirs()

    dependency_mgmt.create_component_symlinks(config, component)

    expected_symlinks = [
        (
            tmp_path / "inventory" / "classes" / "components" / f"{component.name}.yml",
            "class",
        ),
        (
            tmp_path / "inventory" / "classes" / "defaults" / f"{component.name}.yml",
            "default",
        ),
        (tmp_path / "dependencies" / "lib" / "my-component.libjsonnet", "lib"),
    ]

    for path, marker in expected_symlinks:
        # Ensure symlinks exist
        assert path.is_symlink()
        # Ensure symlink targets exist
        assert path.resolve().is_file()
        # Ensure symlinked file contains correct marker content
        with open(path) as f:
            fcontents = f.readlines()
            assert fcontents[0] == marker
    assert capsys.readouterr().out == ""


def _setup_mock_inventory(patch_inventory, aliases={}, omit_version=False):
    components = {
        "test-component": {
            "url": "https://github.com/projectsyn/component-test-component.git",
            "version": "master",
        },
        "other-component": {
            "url": "ssh://git@git.acme.com/some/component.git",
            "version": "v1.0.0",
        },
        "third-component": {
            "url": "https://github.com/projectsyn/component-third-component.git",
            "version": "feat/test",
        },
    }
    if omit_version:
        del components["other-component"]["version"]

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


@patch("commodore.dependency_mgmt._read_components")
@patch("commodore.dependency_mgmt._discover_components")
def test_fetch_components(patch_discover, patch_read, config: Config, tmp_path: Path):
    components = ["component-one", "component-two"]
    patch_discover.return_value = (components, {})
    patch_read.return_value = setup_components_upstream(tmp_path, components)

    dependency_mgmt.fetch_components(config)

    for component in components:
        assert component in config._components
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
    patch_discover, patch_urls, config: Config, tmp_path: Path
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

    dependency_mgmt.fetch_components(config)

    for component in components:
        assert component in config._components
        assert (
            tmp_path / "inventory" / "classes" / "components" / f"{component}.yml"
        ).is_symlink()
        assert (
            tmp_path / "inventory" / "classes" / "defaults" / f"{component}.yml"
        ).is_symlink()
        assert (tmp_path / "dependencies" / component).is_dir()

    for component in other_components:
        assert component not in config._components
        assert not (tmp_path / "dependencies" / component).exists()


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
        os.makedirs(cpath / "class", exist_ok=True)
        with open(cpath / "class" / "defaults.yml", "w") as f:
            f.write("")
        with open(cpath / "class" / f"{directory}.yml", "w") as f:
            f.write("")

    return component_dirs, other_dirs


@patch("commodore.dependency_mgmt._discover_components")
def test_register_components(patch_discover, config: Config, tmp_path: Path):
    component_dirs, other_dirs = _setup_register_components(tmp_path)
    patch_discover.return_value = (component_dirs, {})

    dependency_mgmt.register_components(config)

    component_names = config.get_components().keys()
    for c in component_dirs:
        assert c in component_names
    for c in other_dirs:
        assert c not in component_names


@patch("commodore.dependency_mgmt._discover_components")
def test_register_components_and_aliases(
    patch_discover, config: Config, tmp_path: Path
):
    component_dirs, other_dirs = _setup_register_components(tmp_path)
    alias_data = {"fooer": "foo"}
    patch_discover.return_value = (component_dirs, alias_data)

    dependency_mgmt.register_components(config)

    component_names = config.get_components().keys()
    for c in component_dirs:
        assert c in component_names
    for c in other_dirs:
        assert c not in component_names

    aliases = config.get_component_aliases()
    for alias, cn in alias_data.items():
        if cn in component_dirs:
            assert alias in aliases
            assert aliases[alias] == cn
        else:
            assert alias not in aliases


@patch("commodore.dependency_mgmt._discover_components")
def test_register_unknown_components(
    patch_discover, config: Config, tmp_path: Path, capsys
):
    component_dirs, other_dirs = _setup_register_components(tmp_path)
    unknown_components = ["qux", "quux"]
    component_dirs.extend(unknown_components)
    patch_discover.return_value = (component_dirs, {})

    dependency_mgmt.register_components(config)

    captured = capsys.readouterr()
    for cn in unknown_components:
        assert f"Skipping registration of component {cn}" in captured.out


@patch("commodore.dependency_mgmt._discover_components")
def test_register_dangling_aliases(
    patch_discover, config: Config, tmp_path: Path, capsys
):
    component_dirs, other_dirs = _setup_register_components(tmp_path)
    # add some dangling aliases
    alias_data = {"quxer": "qux", "quuxer": "quux"}
    # generate expected output
    should_miss = sorted(set(alias_data.keys()))
    # add an alias that should work
    alias_data["bazzer"] = "baz"

    patch_discover.return_value = (component_dirs, alias_data)

    dependency_mgmt.register_components(config)

    captured = capsys.readouterr()
    assert (
        f"Dropping alias(es) {should_miss} with missing component(s)." in captured.out
    )


@pytest.mark.parametrize(
    "libname,expected",
    [
        ("test-component.libsonnet", ""),
        ("test-component-lib.libsonnet", ""),
        (
            "lib.libsonnet",
            "Component 'test-component' uses invalid component library name 'lib.libsonnet'. "
            + "Consider using a library alias.",
        ),
    ],
)
def test_validate_component_library_name(tmp_path: Path, libname: str, expected: str):
    if expected == "":
        lpath = Path(tmp_path / "lib" / libname)
        r = dependency_mgmt.validate_component_library_name("test-component", lpath)
        assert lpath == r

    else:
        with pytest.raises(click.ClickException) as e:
            dependency_mgmt.validate_component_library_name(
                "test-component", Path(tmp_path / "lib" / libname)
            )

        assert expected in str(e.value)


@pytest.mark.parametrize(
    "cluster_params,expected",
    [
        (
            {
                "components": {
                    "component-1": {
                        "url": "https://example.com/component-1.git",
                        "version": "v1.2.3",
                    },
                    "component-2": {
                        "url": "https://example.com/component-2.git",
                        "version": "v4.5.6",
                    },
                    "component-3": {
                        "url": "https://example.com/component-3.git",
                        "version": "v7.8.9",
                    },
                },
            },
            "",
        ),
        (
            {
                "components": {
                    "component-1": {
                        "url": "https://example.com/component-1.git",
                        "version": "v1.2.3",
                    },
                    "component_1": {"version": "feat/test"},
                    "component-2": {
                        "url": "https://example.com/component-2.git",
                        "version": "v4.5.6",
                    },
                    "component-3": {
                        "url": "https://example.com/component-3.git",
                        "version": "v7.8.9",
                    },
                },
            },
            "Version override specified for component 'component_1' which has no URL",
        ),
        (
            {
                "components": {
                    "component-1": {
                        "url": "https://example.com/component-1.git",
                        "version": "v1.2.3",
                    },
                    "component_1": {"version": "feat/test"},
                    "component-2": {
                        "url": "https://example.com/component-2.git",
                        "version": "v4.5.6",
                    },
                    "component_2": {"version": "feat/test2"},
                    "component-3": {
                        "url": "https://example.com/component-3.git",
                        "version": "v7.8.9",
                    },
                },
            },
            "Version overrides specified for components 'component_1' and 'component_2' which have no URL",
        ),
    ],
)
def test_verify_component_version_overrides(cluster_params: dict, expected: str):
    if expected == "":
        dependency_mgmt.verify_component_version_overrides(cluster_params)
    else:
        with pytest.raises(click.ClickException) as e:
            dependency_mgmt.verify_component_version_overrides(cluster_params)

        assert expected in str(e)
