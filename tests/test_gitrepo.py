"""
Unit-tests for git
"""

import click
import git
import pytest

from commodore import gitrepo
from pathlib import Path


def test_clone_error(tmp_path: Path):
    inexistent_url = "ssh://git@git.example.com/some/repo.git"
    with pytest.raises(click.ClickException) as excinfo:
        gitrepo.GitRepo.clone(inexistent_url, tmp_path, None)
    assert inexistent_url in str(excinfo.value)


def test_clone_initial_commit(tmp_path: Path):
    git.Repo.init(tmp_path / "repo.git")
    url = f"file:///{tmp_path}/repo.git"

    r = gitrepo.GitRepo.clone(url, tmp_path / "repo", None)

    assert r.repo.head
    assert r.repo.working_tree_dir
    assert r.repo.head.commit.message == "Initial commit"


def test_update_remote(tmp_path: Path):
    new_url = "ssh://git@git.example.com/some/repo.git"
    repo = gitrepo.GitRepo(None, tmp_path, force_init=True)
    repo.remote = new_url
    assert repo.repo.remotes.origin.url == new_url
