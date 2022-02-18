"""
Tests for catalog internals
"""
import copy
from pathlib import Path

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

    git.Repo.init(tmp_path / "repo.git")

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
