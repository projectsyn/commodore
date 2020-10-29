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
from textwrap import dedent

from commodore import dependency_mgmt
from commodore.config import Config
from commodore.component import Component
from commodore.helpers import relsymlink
from commodore.inventory import Inventory


@pytest.fixture
def data():
    """
    Setup test data
    """

    return Config(
        "https://syn.example.com", "token", "ssh://git@git.example.com", False
    )


def test_symlink(tmp_path: Path):
    os.chdir(tmp_path)
    test_file = tmp_path / "test1"
    relsymlink(test_file, tmp_path)
    assert test_file.is_symlink()


def test_override_symlink(tmp_path: Path):
    os.chdir(tmp_path)
    test_file = tmp_path / "test2"
    test_file.touch()
    assert not test_file.is_symlink()
    relsymlink(test_file, tmp_path)
    assert test_file.is_symlink()


def test_create_component_symlinks_fails(data: Config, tmp_path: Path):
    os.chdir(tmp_path)
    component = Component("my-component")
    with pytest.raises(FileNotFoundError):
        dependency_mgmt.create_component_symlinks(data, component)


def test_create_component_symlinks(capsys, data: Config, tmp_path):
    os.chdir(tmp_path)
    component = Component("my-component")
    component.class_file.parent.mkdir(parents=True, exist_ok=True)
    component.class_file.touch()
    component.defaults_file.touch()
    inv = Inventory(work_dir=tmp_path)
    inv.ensure_dirs()

    dependency_mgmt.create_component_symlinks(data, component)

    assert (
        tmp_path / "inventory" / "classes" / "components" / f"{component.name}.yml"
    ).is_symlink()
    assert (
        tmp_path / "inventory" / "classes" / "defaults" / f"{component.name}.yml"
    ).is_symlink()
    assert capsys.readouterr().out == ""


def test_read_component_urls_no_config(data: Config):
    with pytest.raises(click.ClickException) as excinfo:
        dependency_mgmt._read_component_urls(data, [])
    assert "inventory/classes/global/commodore.yml" in str(excinfo)


def test_read_component_urls(data: Config, tmp_path):
    os.chdir(tmp_path)
    component_names = ["component-overwritten", "component-default"]
    inventory_global = Path("inventory/classes/global")
    inventory_global.mkdir(parents=True, exist_ok=True)
    config_file = inventory_global / "commodore.yml"
    override_url = "ssh://git@git.acme.com/some/component.git"
    with open(config_file, "w") as file:
        file.write(
            dedent(
                f"""
            components:
            - name: component-overwritten
              url: {override_url}"""
            )
        )

    components = dependency_mgmt._read_component_urls(data, component_names)

    assert components["component-overwritten"] == override_url
    assert (
        components["component-default"]
        == f"{data.default_component_base}/component-default.git"
    )


@patch("commodore.dependency_mgmt._read_component_urls")
@patch("commodore.dependency_mgmt._discover_components")
def test_fetch_components(patch_discover, patch_urls, data: Config, tmp_path: Path):
    os.chdir(tmp_path)
    components = ["component-one", "component-two"]
    patch_discover.return_value = components
    patch_urls.return_value = {}

    # Prepare minimum component directories
    upstream = Path("upstream")
    for component in components:
        repo_path = upstream / component
        patch_urls.return_value[component] = f"file://#{repo_path.resolve()}"
        repo = git.Repo.init(repo_path)

        class_dir = repo_path / "class"
        class_dir.mkdir(parents=True, exist_ok=True)
        (class_dir / "defaults.yml").touch(exist_ok=True)

        repo.index.add(["class/defaults.yml"])
        repo.index.commit("component defaults")

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


def test_clear_jsonnet_lock_file(tmp_path: Path):
    os.chdir(tmp_path)
    jsonnetfile = Path("jsonnetfile.json")
    jsonnet_lock = Path("jsonnetfile.lock.json")
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
    dependency_mgmt.fetch_jsonnet_libraries()

    assert jsonnet_lock.is_file()
    with open(jsonnet_lock, "r") as file:
        data = json.load(file)
        assert (
            data["dependencies"][0]["version"]
            != "57b4365eacda291b82e0d55ba7eec573a8198dda"
        )


def test_register_components(data: Config, tmp_path: Path):
    os.chdir(tmp_path)
    inv = Inventory(tmp_path)
    inv.ensure_dirs()
    component_dirs = ["foo", "bar", "baz"]
    other_dirs = ["lib", "libs"]
    for directory in component_dirs + other_dirs:
        cpath = tmp_path / "dependencies" / directory
        os.makedirs(cpath, exist_ok=True)
        r = git.Repo.init(cpath)
        r.create_remote("origin", f"ssh://git@example.com/git/{directory}")

    dependency_mgmt.register_components(data)

    component_names = data.get_components().keys()
    for c in component_dirs:
        assert c in component_names
    for c in other_dirs:
        assert c not in component_names
