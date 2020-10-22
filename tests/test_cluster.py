"""
Unit-tests for catalog compilation
"""

import click
from unittest.mock import patch
import pytest

from commodore import compile
from commodore.cluster import Cluster
from commodore.config import Config


@pytest.fixture
def data():
    return {
        "config": Config(
            "https://syn.example.com", "token", "ssh://git@git.example.com", False
        ),
        "cluster": {"tenant": "t-foo"},
        "tenant": {"id": "t-foo"},
    }


def lieutenant_query(api_url, api_token, api_endpoint, api_id):
    if api_endpoint == "clusters":
        return {"id": api_id}

    if api_endpoint == "tenants":
        return {"id": api_id}

    raise click.ClickException(f"call to unexpected API endpoint '#{api_endpoint}'")


@patch("commodore.cluster.lieutenant_query")
def test_no_tenant_reference(test_patch):
    customer_id = "t-wild-fire-234"
    config = Config(
        "https://syn.example.com", "token", "ssh://git@git.example.com", False
    )
    test_patch.side_effect = lieutenant_query
    with pytest.raises(click.ClickException) as err:
        compile.load_cluster_from_api(config, customer_id)
    assert "cluster does not have a tenant reference" in str(err)


def test_cluster_global_git_repo_url(data):
    cluster = Cluster(data["config"], data["cluster"], data["tenant"])
    assert (
        "ssh://git@git.example.com/commodore-defaults.git"
        == cluster.global_git_repo_url
    )

    set_on_tenant = data.copy()
    set_on_tenant["tenant"]["globalGitRepoURL"] = "ssh://git@example.com/tenant.git"
    cluster = Cluster(
        set_on_tenant["config"], set_on_tenant["cluster"], set_on_tenant["tenant"]
    )
    assert "ssh://git@example.com/tenant.git" == cluster.global_git_repo_url


def test_global_git_repo_revision(data):
    cluster = Cluster(data["config"], data["cluster"], data["tenant"])
    assert not cluster.global_git_repo_revision

    set_on_tenant = data.copy()
    set_on_tenant["tenant"]["globalGitRepoRevision"] = "v1.2.3"
    cluster = Cluster(
        set_on_tenant["config"], set_on_tenant["cluster"], set_on_tenant["tenant"]
    )
    assert "v1.2.3" == cluster.global_git_repo_revision

    set_on_cluster = data.copy()
    set_on_cluster["cluster"]["globalGitRepoRevision"] = "v3.2.1"
    cluster = Cluster(
        set_on_cluster["config"], set_on_cluster["cluster"], set_on_cluster["tenant"]
    )
    assert "v3.2.1" == cluster.global_git_repo_revision

    set_on_both = data.copy()
    set_on_both["cluster"]["globalGitRepoRevision"] = "v2.3.1"
    set_on_both["tenant"]["globalGitRepoRevision"] = "v1.2.3"
    cluster = Cluster(
        set_on_both["config"], set_on_both["cluster"], set_on_both["tenant"]
    )
    assert "v2.3.1" == cluster.global_git_repo_revision


def test_config_repo_url(data):
    cluster = Cluster(data["config"], data["cluster"], data["tenant"])
    with pytest.raises(click.ClickException) as err:
        cluster.config_repo_url
    assert " > API did not return a repository URL for tenant 't-foo'" in str(err)

    data["tenant"]["gitRepo"] = {
        "url": "ssh://git@example.com/tenant.git",
    }
    cluster = Cluster(data["config"], data["cluster"], data["tenant"])
    assert "ssh://git@example.com/tenant.git" == cluster.config_repo_url


def test_config_git_repo_revision(data):
    cluster = Cluster(data["config"], data["cluster"], data["tenant"])
    assert not cluster.config_git_repo_revision

    set_on_tenant = data.copy()
    set_on_tenant["tenant"]["gitRepoRevision"] = "v1.2.3"
    cluster = Cluster(
        set_on_tenant["config"], set_on_tenant["cluster"], set_on_tenant["tenant"]
    )
    assert "v1.2.3" == cluster.config_git_repo_revision

    set_on_cluster = data.copy()
    set_on_cluster["cluster"]["gitRepoRevision"] = "v3.2.1"
    cluster = Cluster(
        set_on_cluster["config"], set_on_cluster["cluster"], set_on_cluster["tenant"]
    )
    assert "v3.2.1" == cluster.config_git_repo_revision

    set_on_both = data.copy()
    set_on_both["cluster"]["gitRepoRevision"] = "v2.3.1"
    set_on_both["tenant"]["gitRepoRevision"] = "v1.2.3"
    cluster = Cluster(
        set_on_both["config"], set_on_both["cluster"], set_on_both["tenant"]
    )
    assert "v2.3.1" == cluster.config_git_repo_revision
