import click
import pytest

from pathlib import Path as P
from typing import Dict
from unittest.mock import patch

from commodore import compile
from commodore.config import Config
from commodore.cluster import Cluster

import mock_gitrepo


@pytest.fixture
def config(tmp_path):
    """
    Setup test config object
    """
    return Config(
        tmp_path,
        api_url="https://syn.example.com",
        api_token="token",
    )


def setup_cluster(globalrev=None, tenantrev=None):
    """
    Setup test cluster object
    """
    cluster_apiresp = {
        "id": "c-cluster",
        "tenant": "t-tenant",
        "annotations": {
            "monitoring.syn.tools/sla": "24/7 Reactive",
            "syn.tools/tenant": "t-tenant",
        },
        "displayName": "My very important cluster",
        "facts": {
            "cloud": "aws",
            "distribution": "openshift4",
            "region": "eu-west-1",
        },
        "gitRepo": {
            "deployKey": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDG9a5WwLuwcxMRydNqI4ofuzXucrBKpGOvPV9PO4guj\n",
            # Truncated hostKeys content to only ed25519
            "hostKeys": "gitlab.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAfuCHKVTjquxvt6CM6tdG4SLp1Btn/nOeHHE5UOzRdf",
            "type": "auto",
            "url": "ssh://git@git.example.com/acmecorp/gitops-mycluster.git",
        },
        "installURL": "https://api.syn.vshn.net/install/steward.json?token=<secretToken>",
    }
    tenant_apiresp = {
        "id": "t-tenant",
        "annotations": {
            "monitoring.syn.tools/sla": "24/7 Reactive",
            "syn.tools/tenant": "t-nameless-pond-1234",
        },
        "displayName": "Acme Corp.",
        "gitRepo": {
            "type": "auto",
            "url": "ssh://git@git.example.com/acmecorp/tenant-repo.git",
        },
        "globalGitRepoURL": "ssh://git@git.example.com/acmecorp/gitops-global.git",
    }

    if globalrev is not None:
        cluster_apiresp["globalGitRepoRevision"] = globalrev
    if tenantrev is not None:
        cluster_apiresp["tenantGitRepoRevision"] = tenantrev

    return Cluster(cluster_apiresp, tenant_apiresp)


def assert_result(cluster, repo, repourl, revision, override_revision):
    # Calculate effective checked out revision
    effective_revision = revision
    if override_revision is not None:
        effective_revision = override_revision

    assert repo.remote == repourl
    assert repo.version == effective_revision
    assert repo.call_counts["commit"] == 0
    assert repo.call_counts["checkout"] == 1


@patch.object(compile, "GitRepo", new=mock_gitrepo.GitRepo)
@pytest.mark.parametrize("revision", [None, "ref"])
@pytest.mark.parametrize("override_revision", [None, "oref"])
def test_fetch_global_config(tmp_path: P, config, revision, override_revision):
    # Set revision values
    cluster = setup_cluster(globalrev=revision)
    config.global_repo_revision_override = override_revision

    compile._fetch_global_config(config, cluster)

    repo = config.get_configs()["global"]

    assert_result(
        cluster, repo, cluster.global_git_repo_url, revision, override_revision
    )


@patch.object(compile, "GitRepo", new=mock_gitrepo.GitRepo)
@pytest.mark.parametrize("revision", [None, "ref"])
@pytest.mark.parametrize("override_revision", [None, "oref"])
def test_fetch_customer_config(tmp_path: P, config, revision, override_revision):
    # Set revision values
    cluster = setup_cluster(tenantrev=revision)
    config.tenant_repo_revision_override = override_revision

    compile._fetch_customer_config(config, cluster)

    repo = config.get_configs()["customer"]

    assert_result(cluster, repo, cluster.config_repo_url, revision, override_revision)


@pytest.mark.parametrize(
    "cluster_params,raises",
    [
        ({}, False),
        (
            {
                "components": {
                    "tc1": {
                        "url": "https://example.com/tc1.git",
                        "version": "1",
                    }
                },
                "component_versions": {},
            },
            False,
        ),
        (
            {
                "components": {
                    "tc1": {
                        "url": "https://example.com/tc1.git",
                        "version": "1",
                    }
                },
                "component_versions": {
                    "tc1": {
                        "version": "2",
                    }
                },
            },
            True,
        ),
    ],
)
def test_check_parameters_component_versions(cluster_params: Dict, raises: bool):
    if raises:
        with pytest.raises(click.ClickException) as e:
            compile.check_parameters_component_versions(cluster_params)

        assert (
            "Specifying component versions in parameter `component_versions` is no longer suppported."
            in str(e.value)
        )

    else:
        compile.check_parameters_component_versions(cluster_params)
