"""
Unit-tests for git
"""

import click
import pytest

from commodore import gitrepo
from git import Repo
from pathlib import Path


def test_create_repository(tmp_path: Path):
    repo = gitrepo.create_repository(tmp_path)
    output = gitrepo.stage_all(repo)
    assert output != ""


def test_clone_error(tmp_path: Path):
    inexistent_url = "ssh://git@git.example.com/some/repo.git"
    with pytest.raises(click.ClickException) as excinfo:
        gitrepo.clone_repository(inexistent_url, tmp_path, None)
    assert inexistent_url in str(excinfo.value)


def test_update_remote(tmp_path: Path):
    new_url = "ssh://git@git.example.com/some/repo.git"
    repo = Repo.init(tmp_path)
    repo.create_remote("origin", url="ssh://")
    with pytest.raises(click.ClickException):
        gitrepo.update_remote(repo, new_url)
    assert repo.remotes.origin.url == new_url
