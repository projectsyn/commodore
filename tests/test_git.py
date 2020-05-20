"""
Unit-tests for git
"""

import click
import pytest

from commodore import git
from pathlib import Path


def test_create_repository(tmp_path: Path):
    repo_path = tmp_path / 'test-repo'
    repo_path.mkdir()
    repo = git.create_repository(repo_path)
    output = git.stage_all(repo)
    assert output != ""


def test_clone_error(tmp_path: Path):
    inexistent_url = 'ssh://git@git.example.com/some/repo.git'
    with pytest.raises(click.ClickException) as excinfo:
        git.clone_repository(inexistent_url, tmp_path)
    assert inexistent_url in str(excinfo.value)
