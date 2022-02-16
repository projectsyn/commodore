"""
Unit-tests for git
"""

import click
import pytest

from commodore import gitrepo
from pathlib import Path


def test_create_repository(tmp_path: Path):
    repo = gitrepo.GitRepo.create(tmp_path)
    output = repo.stage_all(repo)
    assert output != ""


def test_clone_error(tmp_path: Path):
    inexistent_url = "ssh://git@git.example.com/some/repo.git"
    with pytest.raises(click.ClickException) as excinfo:
        gitrepo.GitRepo.clone(inexistent_url, tmp_path, None)
    assert inexistent_url in str(excinfo.value)


def test_update_remote(tmp_path: Path):
    new_url = "ssh://git@git.example.com/some/repo.git"
    repo = gitrepo.GitRepo.create(tmp_path)
    repo.remote = new_url
    assert repo.repo.remotes.origin.url == new_url
