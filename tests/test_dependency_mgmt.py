"""
Unit-tests for dependency management
"""

import click
import pytest

from commodore import dependency_mgmt
from commodore.config import Config

from pathlib import Path


@pytest.fixture
def data():
    """
    Setup test data
    """

    return Config("https://syn.example.com", "token", "ssh://git@git.example.com", False)


def test_symlink(tmp_path: Path):
    test_file = tmp_path / "test1"
    dependency_mgmt._relsymlink("./", test_file.name, tmp_path)
    assert test_file.is_symlink()


def test_override_symlink(tmp_path: Path):
    test_file = tmp_path / "test2"
    test_file.touch()
    assert not test_file.is_symlink()
    dependency_mgmt._relsymlink("./", test_file.name, tmp_path)
    assert test_file.is_symlink()


def test_create_component_symlinks_fails(data: Config):
    component_name = "my-component"
    with pytest.raises(click.ClickException) as excinfo:
        dependency_mgmt.create_component_symlinks(data, component_name)
    assert component_name in str(excinfo)


def test_create_legacy_component_symlinks(capsys, data: Config):
    component_name = "my-component"
    target_dir = Path('inventory/classes/components')
    target_dir.mkdir(parents=True, exist_ok=True)
    dependency_mgmt.create_component_symlinks(data, component_name)
    capture = capsys.readouterr()
    assert (target_dir / f"{component_name}.yml").is_symlink()
    assert "Old-style component detected." in capture.out


def test_create_component_symlinks(capsys, data: Config):
    component_name = "my-component"
    class_dir = Path('dependencies') / component_name / "class"
    class_dir.mkdir(parents=True, exist_ok=True)
    (class_dir / f"{component_name}.yml").touch()
    (class_dir / 'defaults.yml').touch()
    target_dir = Path('inventory/classes/components')
    target_dir.mkdir(parents=True, exist_ok=True)
    target_defaults = Path('inventory/classes/defaults')
    target_defaults.mkdir(parents=True, exist_ok=True)
    dependency_mgmt.create_component_symlinks(data, component_name)
    capture = capsys.readouterr()
    assert (target_dir / f"{component_name}.yml").is_symlink()
    assert (target_defaults / f"{component_name}.yml").is_symlink()
    assert capture.out == ""
