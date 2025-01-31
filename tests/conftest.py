"""
Shared test fixtures for all tests
See the pytest docs for more details:
https://docs.pytest.org/en/latest/how-to/fixtures.html#scope-sharing-fixtures-across-classes-modules-packages-or-session
"""

from __future__ import annotations

import multiprocessing
import os

from pathlib import Path
from typing import Protocol

import pytest

from click.testing import CliRunner, Result
from git import Repo

from commodore import cli
from commodore.config import Config
from commodore.gitrepo import GitRepo


class RunnerFunc(Protocol):
    def __call__(self, args: list[str]) -> Result: ...


# For gojsonnet we must use start_method "spawn" for multiprocessing so that the tests don't break
# with pytest-xdist. Since we also use start_method "spawn" in Commodore, this should be fine. We
# set this via a session-scoped autouse fixture, so it's set once when the PyTest session starts.
@pytest.fixture(autouse=True, scope="session")
def init_env():
    multiprocessing.set_start_method("spawn")


@pytest.fixture(autouse=True)
def gitconfig(tmp_path: Path) -> Path:
    """Ensure that tests have a predictable empty gitconfig.

    We set autouse=True, so that the fixture is automatically used for all
    tests. Tests that want to access the mock gitconfig can explicitly specify
    the fixture, so they get the path to the mock gitconfig.
    """
    os.environ["GIT_CONFIG_NOSYSTEM"] = "true"
    os.environ["HOME"] = str(tmp_path)
    os.environ["XDG_CONFIG_HOME"] = str(tmp_path / ".config")
    gitconfig = tmp_path / ".config" / "git" / "config"
    os.makedirs(gitconfig.parent, exist_ok=True)

    return gitconfig


@pytest.fixture
def cli_runner() -> RunnerFunc:
    r = CliRunner()
    return lambda args: r.invoke(cli.commodore, args)


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
    _components: dict[str, Path]
    _packages: dict[str, Path]

    def __init__(self, repo: Repo):
        self._repo = repo
        self._components = {}
        self._packages = {}

    def register_component(self, name: str, target_dir: Path):
        assert name not in self._components
        self._components[name] = target_dir

    def checkout_component(self, name, version):
        assert name in self._components
        assert version == "master"
        self._repo.clone(self._components[name])

    def register_package(self, name: str, target_dir: Path):
        assert name not in self._packages
        self._packages[name] = target_dir

    def checkout_package(self, name, version):
        assert name in self._packages
        assert version == "master"
        self._repo.clone(self._packages[name])

    def get_component(self, name) -> Path:
        return self._components[name]

    @property
    def bare_repo(self) -> GitRepo:
        return self._repo


@pytest.fixture
def mockdep(tmp_path):
    return MockMultiDependency(Repo.init(tmp_path / "repo.git"))


class MockTemplater:
    def __init__(self):
        self.template_version = None
        self.test_cases = []

    def update(self, *args, **kwargs):
        pass


def make_mock_templater(mock_templater, expected_path):
    mt = MockTemplater()

    def mock_from_existing(_config: Config, path: Path):
        assert path == expected_path
        return mt

    mock_templater.from_existing = mock_from_existing

    return mt
