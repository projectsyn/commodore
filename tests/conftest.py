"""
Shared test fixtures for all tests
See the pytest docs for more details:
https://docs.pytest.org/en/latest/how-to/fixtures.html#scope-sharing-fixtures-across-classes-modules-packages-or-session
"""
from pathlib import Path

import pytest

from git import Repo

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


class MockMultiDependency:
    _repo: Repo
    _target_dir: Path
    _name: str

    def __init__(self, repo: Repo):
        self._repo = repo

    def register_component(self, name: str, target_dir: Path):
        self._target_dir = target_dir
        self._name = name

    def checkout_component(self, name, version):
        assert name == self._name
        assert version == "master"
        self._repo.clone(self._target_dir)

    def register_package(self, name: str, target_dir: Path):
        self._target_dir = target_dir
        self._name = f"pkg.{name}"

    def checkout_package(self, name, version):
        assert name == self._name
        assert version == "master"
        self._repo.clone(self._target_dir)


@pytest.fixture
def mockdep(tmp_path):
    return MockMultiDependency(Repo.init(tmp_path / "repo.git"))
