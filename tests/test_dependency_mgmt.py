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
from commodore.config import Config, Component
from commodore.helpers import relsymlink


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
    relsymlink("./", test_file.name, tmp_path)
    assert test_file.is_symlink()


def test_override_symlink(tmp_path: Path):
    os.chdir(tmp_path)
    test_file = tmp_path / "test2"
    test_file.touch()
    assert not test_file.is_symlink()
    relsymlink("./", test_file.name, tmp_path)
    assert test_file.is_symlink()


def test_create_component_symlinks_fails(data: Config, tmp_path: Path):
    os.chdir(tmp_path)
    component = Component(
        name="my-component",
        repo=None,
        version="master",
        repo_url=None,
    )
    with pytest.raises(FileNotFoundError):
        dependency_mgmt.create_component_symlinks(data, component)


def test_create_legacy_component_symlinks(capsys, data: Config, tmp_path):
    os.chdir(tmp_path)
    component = Component(
        name="my-component",
        repo=None,
        version="master",
        repo_url=None,
    )
    target_dir = Path("inventory/classes/components")
    target_dir.mkdir(parents=True, exist_ok=True)
    dependency_mgmt.create_component_symlinks(data, component)
    capture = capsys.readouterr()
    assert (target_dir / f"{component.name}.yml").is_symlink()
    assert "Old-style component detected." in capture.out


def test_create_component_symlinks(capsys, data: Config, tmp_path):
    os.chdir(tmp_path)
    component = Component(
        name="my-component",
        repo=None,
        version="master",
        repo_url=None,
    )
    class_dir = Path("dependencies") / component.name / "class"
    class_dir.mkdir(parents=True, exist_ok=True)
    (class_dir / f"{component.name}.yml").touch()
    (class_dir / "defaults.yml").touch()
    target_dir = Path("inventory/classes/components")
    target_dir.mkdir(parents=True, exist_ok=True)
    target_defaults = Path("inventory/classes/defaults")
    target_defaults.mkdir(parents=True, exist_ok=True)
    dependency_mgmt.create_component_symlinks(data, component)
    capture = capsys.readouterr()
    assert (target_dir / f"{component.name}.yml").is_symlink()
    assert (target_defaults / f"{component.name}.yml").is_symlink()
    assert capture.out == ""


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
    override = components[0]
    default = components[1]
    assert override.repo_url == override_url
    assert default.repo_url == f"{data.default_component_base}/{default.name}.git"


@patch("commodore.dependency_mgmt._discover_components")
@patch("commodore.dependency_mgmt._read_component_urls")
@patch("commodore.git.clone_repository")
def test_fetch_components(
    patch_discover, patch_urls, patch_clone, data: Config, tmp_path
):
    os.chdir(tmp_path)
    components = ["component-one", "component-two"]
    # Prepare minimum component directories
    for component in components:
        class_dir = Path("dependencies") / component / "class"
        class_dir.mkdir(parents=True, exist_ok=True)
        (class_dir / "defaults.yml").touch(exist_ok=True)
    patch_discover.return_value = components
    patch_urls.return_value = [
        Component(
            name=c,
            repo=None,
            repo_url="mock-url",
            version="master",
        )
        for c in components
    ]
    dependency_mgmt.fetch_components(data)
    print(data._components)
    for component in components:
        assert component in data._components
        assert (Path("inventory/classes/components") / f"{component}.yml").is_symlink()
        assert (Path("inventory/classes/defaults") / f"{component}.yml").is_symlink()
        assert data.get_component_repo(component) is not None


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
    component_dirs = ["foo", "bar", "baz"]
    other_dirs = ["lib", "libs"]
    for directory in component_dirs + other_dirs:
        cpath = Path("dependencies", directory)
        os.makedirs(cpath, exist_ok=True)
        r = git.Repo.init(cpath)
        r.create_remote("origin", f"ssh://git@example.com/git/{directory}")

    dependency_mgmt.register_components(data)

    component_names = data.get_components().keys()
    for c in component_dirs:
        assert c in component_names
    for c in other_dirs:
        assert c not in component_names
