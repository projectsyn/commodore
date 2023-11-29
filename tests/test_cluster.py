"""
Unit-tests for catalog compilation
"""

import click
from unittest.mock import patch
import pytest

from commodore import compile
from commodore.cluster import Cluster


def lieutenant_query(api_url, api_token, api_endpoint, api_id, params={}, timeout=5):
    if api_endpoint == "clusters":
        return {"id": api_id}

    if api_endpoint == "tenants":
        return {"id": api_id}

    raise click.ClickException(f"call to unexpected API endpoint '#{api_endpoint}'")


@patch("commodore.cluster.lieutenant_query")
def test_no_tenant_reference(query_patch, config, tmp_path):
    customer_id = "t-wild-fire-234"
    query_patch.side_effect = lieutenant_query
    with pytest.raises(click.ClickException) as err:
        compile.load_cluster_from_api(config, customer_id)
    assert "cluster does not have a tenant reference" in str(err)


def test_cluster_global_git_repo_url(api_data):
    cluster = Cluster(api_data["cluster"], api_data["tenant"])
    with pytest.raises(click.ClickException) as err:
        _ = cluster.global_git_repo_url
    assert "URL of the global git repository is missing on tenant 't-foo'" in str(err)

    set_on_tenant = api_data.copy()
    set_on_tenant["tenant"]["globalGitRepoURL"] = "ssh://git@example.com/tenant.git"
    cluster = Cluster(set_on_tenant["cluster"], set_on_tenant["tenant"])
    assert cluster.global_git_repo_url == "ssh://git@example.com/tenant.git"


def test_global_git_repo_revision(api_data):
    cluster = Cluster(api_data["cluster"], api_data["tenant"])
    assert not cluster.global_git_repo_revision

    set_on_tenant = api_data.copy()
    set_on_tenant["tenant"]["globalGitRepoRevision"] = "v1.2.3"
    cluster = Cluster(set_on_tenant["cluster"], set_on_tenant["tenant"])
    assert cluster.global_git_repo_revision == "v1.2.3"

    set_on_cluster = api_data.copy()
    set_on_cluster["cluster"]["globalGitRepoRevision"] = "v3.2.1"
    cluster = Cluster(set_on_cluster["cluster"], set_on_cluster["tenant"])
    assert cluster.global_git_repo_revision == "v3.2.1"

    set_on_both = api_data.copy()
    set_on_both["cluster"]["globalGitRepoRevision"] = "v2.3.1"
    set_on_both["tenant"]["globalGitRepoRevision"] = "v1.2.3"
    cluster = Cluster(set_on_both["cluster"], set_on_both["tenant"])
    assert cluster.global_git_repo_revision == "v2.3.1"


def test_config_repo_url(api_data):
    cluster = Cluster(api_data["cluster"], api_data["tenant"])
    with pytest.raises(click.ClickException) as err:
        _ = cluster.config_repo_url
    assert " > API did not return a repository URL for tenant 't-foo'" in str(err)

    api_data["tenant"]["gitRepo"] = {
        "url": "ssh://git@example.com/tenant.git",
    }
    cluster = Cluster(api_data["cluster"], api_data["tenant"])
    assert cluster.config_repo_url == "ssh://git@example.com/tenant.git"


def test_config_git_repo_revision(api_data):
    cluster = Cluster(api_data["cluster"], api_data["tenant"])
    assert not cluster.config_git_repo_revision

    set_on_tenant = api_data.copy()
    set_on_tenant["tenant"]["tenantGitRepoRevision"] = "v1.2.3"
    cluster = Cluster(set_on_tenant["cluster"], set_on_tenant["tenant"])
    assert cluster.config_git_repo_revision == "v1.2.3"

    set_on_cluster = api_data.copy()
    set_on_cluster["cluster"]["tenantGitRepoRevision"] = "v3.2.1"
    cluster = Cluster(set_on_cluster["cluster"], set_on_cluster["tenant"])
    assert cluster.config_git_repo_revision == "v3.2.1"

    set_on_both = api_data.copy()
    set_on_both["cluster"]["tenantGitRepoRevision"] = "v2.3.1"
    set_on_both["tenant"]["tenantGitRepoRevision"] = "v1.2.3"
    cluster = Cluster(set_on_both["cluster"], set_on_both["tenant"])
    assert cluster.config_git_repo_revision == "v2.3.1"


def test_catalog_repo_url(api_data):
    # The `api_data` test fixtures includes a catalog repo url. Clear it here to test
    # the error case.
    del api_data["cluster"]["gitRepo"]
    cluster = Cluster(api_data["cluster"], api_data["tenant"])
    with pytest.raises(click.ClickException) as err:
        _ = cluster.catalog_repo_url
    assert " > API did not return a repository URL for cluster 'c-bar'" in str(err)

    api_data["cluster"]["gitRepo"] = {
        "url": "ssh://git@example.com/catalog.git",
    }
    cluster = Cluster(api_data["cluster"], api_data["tenant"])
    assert cluster.catalog_repo_url == "ssh://git@example.com/catalog.git"


def test_tenant_id(api_data):
    cluster = Cluster(api_data["cluster"], api_data["tenant"])
    assert cluster.tenant_id == "t-foo"


def test_tenant_display_name(api_data):
    cluster = Cluster(api_data["cluster"], api_data["tenant"])
    assert cluster.tenant_display_name == "Foo Inc."


def test_id(api_data):
    cluster = Cluster(api_data["cluster"], api_data["tenant"])
    assert cluster.id == "c-bar"


def test_display_name(api_data):
    cluster = Cluster(api_data["cluster"], api_data["tenant"])
    assert cluster.display_name == "Foo Inc. Bar Cluster"


def test_facts(api_data):
    # The `api_data` test fixture sets some facts by default. We clear those here to
    # have a clean base to test the facts logic.
    del api_data["cluster"]["facts"]
    cluster = Cluster(api_data["cluster"], api_data["tenant"])
    assert cluster.facts == {}

    facts = {
        "fact_a": "value_a",
        "fact_b": "value_b",
    }
    api_data["cluster"]["facts"] = facts.copy()
    cluster = Cluster(api_data["cluster"], api_data["tenant"])
    assert cluster.facts == facts


@pytest.mark.parametrize(
    "dynamic_facts",
    [
        {},
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
def test_dynamic_facts(api_data, dynamic_facts):
    # The `api_data` test fixture contains some dynamic facts by default. We clear those
    # to ensure a clean base for testing the dynamic facts logic.
    del api_data["cluster"]["dynamicFacts"]
    cluster = Cluster(api_data["cluster"], api_data["tenant"])
    assert {} == cluster.dynamic_facts

    api_data["cluster"]["dynamicFacts"] = dynamic_facts.copy()
    cluster = Cluster(api_data["cluster"], api_data["tenant"])
    assert dynamic_facts == cluster.dynamic_facts


@pytest.mark.parametrize(
    "dynfacts,fallback",
    [
        ({}, {}),
        ({}, {"foo": "bar"}),
        ({"foo": "bar"}, {"baz": "qux"}),
        (None, {}),
        (None, {"foo": "bar"}),
    ],
)
def test_dynamic_facts_fallback(api_data, dynfacts, fallback):
    # The `api_data` test fixture contains some dynamic facts by default. We clear those
    # to ensure a clean base for testing the dynamic facts logic.
    del api_data["cluster"]["dynamicFacts"]
    cluster = Cluster(api_data["cluster"], api_data["tenant"])
    assert {} == cluster.dynamic_facts

    if dynfacts is not None:
        api_data["cluster"]["dynamicFacts"] = dynfacts.copy()
    cluster = Cluster(api_data["cluster"], api_data["tenant"], fallback)
    if dynfacts is not None:
        assert dynfacts == cluster.dynamic_facts
    else:
        assert fallback == cluster.dynamic_facts
