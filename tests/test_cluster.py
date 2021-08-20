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
        "cluster": {
            "id": "c-bar",
            "tenant": "t-foo",
            "displayName": "Foo Inc. Bar cluster",
        },
        "tenant": {"id": "t-foo", "displayName": "Foo Inc."},
    }


def lieutenant_query(api_url, api_token, api_endpoint, api_id):
    if api_endpoint == "clusters":
        return {"id": api_id}

    if api_endpoint == "tenants":
        return {"id": api_id}

    raise click.ClickException(f"call to unexpected API endpoint '#{api_endpoint}'")


@patch("commodore.cluster.lieutenant_query")
def test_no_tenant_reference(test_patch, tmp_path):
    customer_id = "t-wild-fire-234"
    config = Config(
        tmp_path,
        api_url="https://syn.example.com",
        api_token="token",
    )
    test_patch.side_effect = lieutenant_query
    with pytest.raises(click.ClickException) as err:
        compile.load_cluster_from_api(config, customer_id)
    assert "cluster does not have a tenant reference" in str(err)


def test_cluster_global_git_repo_url(data):
    cluster = Cluster(data["cluster"], data["tenant"])
    with pytest.raises(click.ClickException) as err:
        _ = cluster.global_git_repo_url
    assert "URL of the global git repository is missing on tenant 't-foo'" in str(err)

    set_on_tenant = data.copy()
    set_on_tenant["tenant"]["globalGitRepoURL"] = "ssh://git@example.com/tenant.git"
    cluster = Cluster(set_on_tenant["cluster"], set_on_tenant["tenant"])
    assert "ssh://git@example.com/tenant.git" == cluster.global_git_repo_url


def test_global_git_repo_revision(data):
    cluster = Cluster(data["cluster"], data["tenant"])
    assert not cluster.global_git_repo_revision

    set_on_tenant = data.copy()
    set_on_tenant["tenant"]["globalGitRepoRevision"] = "v1.2.3"
    cluster = Cluster(set_on_tenant["cluster"], set_on_tenant["tenant"])
    assert "v1.2.3" == cluster.global_git_repo_revision

    set_on_cluster = data.copy()
    set_on_cluster["cluster"]["globalGitRepoRevision"] = "v3.2.1"
    cluster = Cluster(set_on_cluster["cluster"], set_on_cluster["tenant"])
    assert "v3.2.1" == cluster.global_git_repo_revision

    set_on_both = data.copy()
    set_on_both["cluster"]["globalGitRepoRevision"] = "v2.3.1"
    set_on_both["tenant"]["globalGitRepoRevision"] = "v1.2.3"
    cluster = Cluster(set_on_both["cluster"], set_on_both["tenant"])
    assert "v2.3.1" == cluster.global_git_repo_revision


def test_config_repo_url(data):
    cluster = Cluster(data["cluster"], data["tenant"])
    with pytest.raises(click.ClickException) as err:
        cluster.config_repo_url
    assert " > API did not return a repository URL for tenant 't-foo'" in str(err)

    data["tenant"]["gitRepo"] = {
        "url": "ssh://git@example.com/tenant.git",
    }
    cluster = Cluster(data["cluster"], data["tenant"])
    assert "ssh://git@example.com/tenant.git" == cluster.config_repo_url


def test_config_git_repo_revision(data):
    cluster = Cluster(data["cluster"], data["tenant"])
    assert not cluster.config_git_repo_revision

    set_on_tenant = data.copy()
    set_on_tenant["tenant"]["tenantGitRepoRevision"] = "v1.2.3"
    cluster = Cluster(set_on_tenant["cluster"], set_on_tenant["tenant"])
    assert "v1.2.3" == cluster.config_git_repo_revision

    set_on_cluster = data.copy()
    set_on_cluster["cluster"]["tenantGitRepoRevision"] = "v3.2.1"
    cluster = Cluster(set_on_cluster["cluster"], set_on_cluster["tenant"])
    assert "v3.2.1" == cluster.config_git_repo_revision

    set_on_both = data.copy()
    set_on_both["cluster"]["tenantGitRepoRevision"] = "v2.3.1"
    set_on_both["tenant"]["tenantGitRepoRevision"] = "v1.2.3"
    cluster = Cluster(set_on_both["cluster"], set_on_both["tenant"])
    assert "v2.3.1" == cluster.config_git_repo_revision


def test_catalog_repo_url(data):
    cluster = Cluster(data["cluster"], data["tenant"])
    with pytest.raises(click.ClickException) as err:
        cluster.catalog_repo_url
    assert " > API did not return a repository URL for cluster 'c-bar'" in str(err)

    data["cluster"]["gitRepo"] = {
        "url": "ssh://git@example.com/catalog.git",
    }
    cluster = Cluster(data["cluster"], data["tenant"])
    assert "ssh://git@example.com/catalog.git" == cluster.catalog_repo_url


def test_tenant_id(data):
    cluster = Cluster(data["cluster"], data["tenant"])
    assert "t-foo" == cluster.tenant_id


def test_tenant_display_name(data):
    cluster = Cluster(data["cluster"], data["tenant"])
    assert "Foo Inc." == cluster.tenant_display_name


def test_id(data):
    cluster = Cluster(data["cluster"], data["tenant"])
    assert "c-bar" == cluster.id


def test_display_name(data):
    cluster = Cluster(data["cluster"], data["tenant"])
    assert "Foo Inc. Bar cluster" == cluster.display_name


def test_facts(data):
    cluster = Cluster(data["cluster"], data["tenant"])
    assert {} == cluster.facts

    facts = {
        "fact_a": "value_a",
        "fact_b": "value_b",
    }
    data["cluster"]["facts"] = facts.copy()
    cluster = Cluster(data["cluster"], data["tenant"])
    assert facts == cluster.facts


@pytest.mark.parametrize(
    "dynamic_facts",
    [
        {
            "kubernetes_version": {
                "major": "1",
                "minor": "21",
                "gitVersion": "v1.21.3",
            }
        },
        {
            "kubernetes_version": {
                "major": "1",
                "minor": "20",
                "gitVersion": "v1.20.0+558d959",
            }
        },
        {
            "kubernetes_version": {
                "major": "1",
                "minor": "20",
                "gitVersion": "v1.20.7-eks-d88609",
            }
        },
        {
            "nodes": 20,
            "node_labels": {
                "node1": {"a": "a"},
                "node2": {"b": "b"},
                "node3": {"c": "c"},
            },
            "test_list": [1, 2, 3],
        },
    ],
)
def test_dynamic_facts(data, dynamic_facts):
    cluster = Cluster(data["cluster"], data["tenant"])
    assert {} == cluster.dynamic_facts

    data["cluster"]["dynamicFacts"] = dynamic_facts.copy()
    cluster = Cluster(data["cluster"], data["tenant"])
    assert dynamic_facts == cluster.dynamic_facts
