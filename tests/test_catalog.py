"""
Tests for catalog internals
"""
import copy
from pathlib import Path
from unittest.mock import patch

import click
import git
import pytest

from commodore import catalog
from commodore.config import Config
from commodore.cluster import Cluster

cluster_resp = {
    "id": "c-test",
    "tenant": "t-test",
    "displayName": "test-cluster",
    "facts": {
        "cloud": "local",
        "distribution": "k3s",
    },
    "gitRepo": {
        "url": "ssh://git@github.com/projectsyn/test-cluster-catalog.git",
    },
}

tenant_resp = {
    "id": "t-test",
    "displayName": "Test tenant",
    "gitRepo": {
        "url": "https://github.com/projectsyn/test-tenant.git",
    },
    "globalGitRepoURL": "https://github.com/projectsyn/commodore-defaults.git",
    "globalGitRepoRevision": "v0.12.0",
}


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(
        tmp_path,
        api_url="https://syn.example.com",
        api_token="token",
        username="John Doe",
        usermail="john.doe@example.com",
    )


@pytest.fixture
def cluster() -> Cluster:
    return Cluster(
        cluster_resp,
        tenant_resp,
    )


@pytest.fixture
def inexistent_cluster() -> Cluster:
    cr = copy.deepcopy(cluster_resp)
    cr["gitRepo"]["url"] = "https://git.example.org/cluster-catalog.git"
    return Cluster(
        cr,
        tenant_resp,
    )


@pytest.fixture
def fresh_cluster(tmp_path: Path) -> Cluster:
    cr = copy.deepcopy(cluster_resp)

    git.Repo.init(tmp_path / "repo.git", bare=True)

    cr["gitRepo"]["url"] = f"file:///{tmp_path}/repo.git"
    return Cluster(
        cr,
        tenant_resp,
    )


def test_catalog_commit_message(tmp_path: Path):
    config = Config(
        tmp_path,
        api_url="https://syn.example.com",
        api_token="token",
    )

    commit_message = catalog._render_catalog_commit_msg(config)
    assert not commit_message.startswith("\n")
    assert commit_message.startswith("Automated catalog update from Commodore\n\n")


def test_fetch_catalog_inexistent(
    tmp_path: Path, config: Config, inexistent_cluster: Cluster
):
    with pytest.raises(Exception) as e:
        catalog.fetch_catalog(config, inexistent_cluster)

    assert inexistent_cluster.catalog_repo_url in str(e.value)


def test_fetch_catalog_initial_commit_for_empty_repo(
    tmp_path: Path, config: Config, fresh_cluster: Cluster
):
    r = catalog.fetch_catalog(config, fresh_cluster)

    assert r.repo.head
    assert r.working_tree_dir
    assert r.repo.head.commit.message == "Initial commit"


def setup_catalog_for_push(config: Config, cluster: Cluster):
    repo = catalog.fetch_catalog(config, cluster)
    with open(repo.working_tree_dir / "test.txt", "w") as f:
        f.writelines(["foo"])

    repo.stage_files(["test.txt"])

    return repo


@pytest.mark.parametrize("push", [True, False])
@pytest.mark.parametrize("local", [True, False])
def test_push_catalog(
    capsys,
    tmp_path: Path,
    config: Config,
    fresh_cluster: Cluster,
    push: bool,
    local: bool,
):
    repo = setup_catalog_for_push(config, fresh_cluster)

    config.push = push
    config.local = local

    catalog._push_catalog(config, repo, "Add test.txt")

    upstream = git.Repo(tmp_path / "repo.git")
    captured = capsys.readouterr()

    if local:
        assert len(upstream.branches) == 0
        assert repo.repo.untracked_files == ["test.txt"]
        assert not repo.repo.is_dirty()
        assert "Skipping commit+push to catalog in local mode..." in captured.out
    elif push:
        assert upstream.active_branch.commit.message == "Add test.txt"
        assert repo.repo.untracked_files == []
        assert not repo.repo.is_dirty()
        assert "Commiting changes..." in captured.out
        assert "Pushing catalog to remote..." in captured.out
    else:
        assert len(upstream.branches) == 0
        assert repo.repo.untracked_files == []
        assert repo.repo.is_dirty()
        assert ("test.txt", 0) in repo.repo.index.entries
        assert "Skipping commit+push to catalog..." in captured.out


@pytest.mark.parametrize("interactive", ["y", "n"])
@patch("click.confirm")
def test_push_catalog_interactive(
    mock_confirm,
    capsys,
    tmp_path: Path,
    config: Config,
    fresh_cluster: Cluster,
    interactive: str,
):
    repo = setup_catalog_for_push(config, fresh_cluster)

    config.push = True
    config.interactive = True
    mock_confirm.return_value = interactive == "y"

    catalog._push_catalog(config, repo, "Add test.txt")

    upstream = git.Repo(tmp_path / "repo.git")
    captured = capsys.readouterr()

    if interactive == "y":
        assert upstream.active_branch.commit.message == "Add test.txt"
        assert repo.repo.untracked_files == []
        assert not repo.repo.is_dirty()
        assert "Commiting changes..." in captured.out
        assert "Pushing catalog to remote..." in captured.out
    else:
        assert len(upstream.branches) == 0
        assert repo.repo.untracked_files == []
        assert repo.repo.is_dirty()
        assert ("test.txt", 0) in repo.repo.index.entries
        assert "Skipping commit+push to catalog..." in captured.out


def test_push_catalog_giterror(config: Config, fresh_cluster: Cluster):
    repo = setup_catalog_for_push(config, fresh_cluster)

    config.push = True
    repo.remote = "file:///path/to/repo.git"

    with pytest.raises(click.ClickException) as e:
        catalog._push_catalog(config, repo, "Add test.txt")
        assert (
            "Failed to push to the catalog repository: Git exited with status code"
            in str(e)
        )


def test_push_catalog_remoteerror(
    tmp_path: Path, config: Config, fresh_cluster: Cluster
):
    repo = setup_catalog_for_push(config, fresh_cluster)

    config.push = True
    hook_path = tmp_path / "repo.git" / "hooks" / "pre-receive"
    with open(hook_path, "w") as hookf:
        hookf.write("#!/bin/sh\necho 'Push denied'\nexit 1")

    hook_path.chmod(0o755)

    with pytest.raises(click.ClickException) as e:
        catalog._push_catalog(config, repo, "Add test.txt")
        assert (
            "Failed to push to the catalog repository: [remote rejected] (pre-receive hook declined)"
            in str(e)
        )
