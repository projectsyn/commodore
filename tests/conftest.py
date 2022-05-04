"""
Shared test fixtures for all tests
See the pytest docs for more details:
https://docs.pytest.org/en/latest/how-to/fixtures.html#scope-sharing-fixtures-across-classes-modules-packages-or-session
"""

import pytest

from commodore.config import Config


@pytest.fixture
def config(tmp_path):
    """
    Setup test Commodore config
    """

    return Config(
        tmp_path,
        api_url="https://syn.example.com",
        api_token="token",
        username="John Doe",
        usermail="john.doe@example.com",
    )


@pytest.fixture
def api_data():
    """
    Setup test Lieutenant API data
    """

    tenant = {
        "id": "t-foo",
        "displayName": "Foo Inc.",
    }
    cluster = {
        "id": "c-bar",
        "displayName": "Foo Inc. Bar Cluster",
        "tenant": tenant["id"],
        "facts": {
            "distribution": "rancher",
            "cloud": "cloudscale",
        },
        "dynamicFacts": {
            "kubernetes_version": {
                "major": "1",
                "minor": "21",
                "gitVersion": "v1.21.3",
            }
        },
        "gitRepo": {
            "url": "ssh://git@git.example.com/cluster-catalogs/mycluster",
        },
    }
    return {
        "cluster": cluster,
        "tenant": tenant,
    }
