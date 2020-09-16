"""
Unit-tests for dependency management
"""

import os
import click
import pytest
from unittest.mock import patch
from pathlib import Path

from commodore import dependency_mgmt
from commodore.config import Config, Component
from commodore.helpers import relsymlink


@pytest.fixture
def data():
    """
    Setup test data
    """

    return Config("https://syn.example.com", "token", "ssh://git@git.example.com", False)


def test_symlink(tmp_path: Path):
    os.chdir(tmp_path)
    test_file = tmp_path / 'test1'
    relsymlink('./', test_file.name, tmp_path)
    assert test_file.is_symlink()


def test_override_symlink(tmp_path: Path):
    os.chdir(tmp_path)
    test_file = tmp_path / 'test2'
    test_file.touch()
    assert not test_file.is_symlink()
    relsymlink('./', test_file.name, tmp_path)
    assert test_file.is_symlink()


def test_create_component_symlinks_fails(data: Config, tmp_path: Path):
    os.chdir(tmp_path)
    component = Component(
        name='my-component',
        repo=None,
        version='master',
        repo_url=None,
    )
    with pytest.raises(FileNotFoundError):
        dependency_mgmt.create_component_symlinks(data, component)


def test_create_legacy_component_symlinks(capsys, data: Config, tmp_path):
    os.chdir(tmp_path)
    component = Component(
        name='my-component',
        repo=None,
        version='master',
        repo_url=None,
    )
    target_dir = Path('inventory/classes/components')
    target_dir.mkdir(parents=True, exist_ok=True)
    dependency_mgmt.create_component_symlinks(data, component)
    capture = capsys.readouterr()
    assert (target_dir / f"{component.name}.yml").is_symlink()
    assert 'Old-style component detected.' in capture.out


def test_create_component_symlinks(capsys, data: Config, tmp_path):
    os.chdir(tmp_path)
    component = Component(
        name='my-component',
        repo=None,
        version='master',
        repo_url=None,
    )
    class_dir = Path('dependencies') / component.name / 'class'
    class_dir.mkdir(parents=True, exist_ok=True)
    (class_dir / f"{component.name}.yml").touch()
    (class_dir / 'defaults.yml').touch()
    target_dir = Path('inventory/classes/components')
    target_dir.mkdir(parents=True, exist_ok=True)
    target_defaults = Path('inventory/classes/defaults')
    target_defaults.mkdir(parents=True, exist_ok=True)
    dependency_mgmt.create_component_symlinks(data, component)
    capture = capsys.readouterr()
    assert (target_dir / f"{component.name}.yml").is_symlink()
    assert (target_defaults / f"{component.name}.yml").is_symlink()
    assert capture.out == ''


def test_read_component_urls_no_config(data: Config):
    with pytest.raises(click.ClickException) as excinfo:
        dependency_mgmt._read_component_urls(data, [])
    assert 'inventory/classes/global/commodore.yml' in str(excinfo)


def test_read_component_urls(data: Config, tmp_path):
    os.chdir(tmp_path)
    component_names = ['component-overwritten', 'component-default']
    inventory_global = Path('inventory/classes/global')
    inventory_global.mkdir(parents=True, exist_ok=True)
    config_file = inventory_global / 'commodore.yml'
    override_url = 'ssh://git@git.acme.com/some/component.git'
    with open(config_file, 'w') as file:
        file.write(f"""components:
- name: component-overwritten
  url: {override_url}
""")

    components = dependency_mgmt._read_component_urls(data, component_names)
    override = components[0]
    default = components[1]
    assert override.repo_url == override_url
    assert default.repo_url == \
        f"{data.default_component_base}/{default.name}.git"


@patch('commodore.dependency_mgmt._discover_components')
@patch('commodore.dependency_mgmt._read_component_urls')
@patch('commodore.git.clone_repository')
def test_fetch_components(patch_discover, patch_urls, patch_clone, data: Config, tmp_path):
    os.chdir(tmp_path)
    components = ['component-one', 'component-two']
    # Prepare minimum component directories
    for component in components:
        class_dir = Path('dependencies') / component / 'class'
        class_dir.mkdir(parents=True, exist_ok=True)
        (class_dir / 'defaults.yml').touch(exist_ok=True)
    patch_discover.return_value = components
    patch_urls.return_value = [
        Component(
            name=c,
            repo=None,
            repo_url='mock-url',
            version='master',
        ) for c in components]
    dependency_mgmt.fetch_components(data)
    print(data._components)
    for component in components:
        assert component in data._components
        assert (Path('inventory/classes/components') / f"{component}.yml").is_symlink()
        assert (Path('inventory/classes/defaults') / f"{component}.yml").is_symlink()
        assert data.get_component_repo(component) is not None
