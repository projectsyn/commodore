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


def test_read_component_urls_no_config(data: Config):
    with pytest.raises(click.ClickException) as excinfo:
        dependency_mgmt._read_component_urls(data, [])
    assert "inventory/classes/global/commodore.yml" in str(excinfo)


def _setup_read_component_urls(data: Config):
    file = data.config_file
    file.parent.mkdir(parents=True, exist_ok=True)
    with open(file, "w") as file:
        file.write(
            dedent(
                """
            components:
            - name: component-overwritten
              url: ssh://git@git.acme.com/some/component.git
                """
            )
        )


def test_read_component_urls(data: Config):
    _setup_read_component_urls(data)
    components = dependency_mgmt._read_component_urls(data, ["component-overwritten"])

    assert (
        components["component-overwritten"]
        == "ssh://git@git.acme.com/some/component.git"
    )


def test_read_component_urls_missing_component(data: Config):
    _setup_read_component_urls(data)
    with pytest.raises(click.ClickException) as e:
        dependency_mgmt._read_component_urls(data, ["component-missing"])

    assert "No url for component 'component-missing'" in str(e)


@patch("commodore.dependency_mgmt._read_component_urls")
@patch("commodore.dependency_mgmt._discover_components")
def test_fetch_components(patch_discover, patch_urls, data: Config, tmp_path: Path):
    components = ["component-one", "component-two"]
    patch_discover.return_value = (components, {})
    patch_urls.return_value = setup_components_upstream(tmp_path, components)

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


@patch("commodore.dependency_mgmt._read_component_urls")
@patch("commodore.dependency_mgmt._discover_components")
def test_fetch_components_is_minimal(
    patch_discover, patch_urls, data: Config, tmp_path: Path
):
    components = ["component-one", "component-two"]
    other_components = ["component-three", "component-four"]
    patch_discover.return_value = (components, {})
    patch_urls.return_value = {}
    patch_urls.return_value = setup_components_upstream(tmp_path, components)
    # Setup upstreams for components which are not included
    extra_urls = setup_components_upstream(tmp_path, other_components)
    for cn, url in extra_urls.items():
        patch_urls.return_value[cn] = url

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
        jf_contents = json.load(jf)
        assert jf_contents["version"] == 1
        assert jf_contents["legacyImports"]
        deps = jf_contents["dependencies"]
        for dep in deps:
            assert dep["source"]["local"]["directory"] in dirs


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


def test_set_component_overrides_version(tmp_path: Path, data: Config):
    data.inventory.ensure_dirs()
    c = Component(
        "argocd",
        repo_url="https://github.com/projectsyn/component-argocd",
        work_dir=tmp_path,
    )
    c.checkout()
    data.register_component(c)

    versions = {
        "argocd": {
            "version": "component-defs-in-applications",
        }
    }

    dependency_mgmt.set_component_overrides(data, versions)

    assert not c.repo.head.is_detached
    assert c.repo.head.ref.name == versions["argocd"]["version"]


def test_set_component_overrides_url(tmp_path: Path, data: Config):
    data.inventory.ensure_dirs()
    c = Component(
        "argocd",
        repo_url="https://github.com/projectsyn/component-argocd",
        work_dir=tmp_path,
    )
    c.checkout()
    data.register_component(c)

    # create local upstream
    local_upstream = tmp_path / "upstream"
    os.makedirs(local_upstream, exist_ok=True)
    git.Repo.init(local_upstream, bare=True)
    c.repo.create_remote("local", f"file://{local_upstream}")
    c.repo.remote(name="local").push("master")

    versions = {"argocd": {"url": f"file://{local_upstream}"}}

    dependency_mgmt.set_component_overrides(data, versions)

    origin_urls = list(c.repo.remote().urls)
    assert len(origin_urls) == 1
    print(origin_urls[0])
    assert origin_urls[0] == f"file://{local_upstream}"
