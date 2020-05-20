"""
Unit-tests for dependency management
"""

import click
import os
import pytest

from commodore import dependency_mgmt
from pathlib import Path


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
