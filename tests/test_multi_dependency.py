from __future__ import annotations

from pathlib import Path

import pytest

from git import Repo
from url_normalize.tools import deconstruct_url

from commodore import multi_dependency

from test_gitrepo import setup_remote


CASES = [
    (
        "https://github.com/projectsyn/component-argocd.git",
        "github.com/projectsyn/component-argocd.git",
    ),
    (
        "git@github.com:projectsyn/component-argocd.git",
        "github.com/projectsyn/component-argocd.git",
    ),
    (
        "ssh://git@github.com/projectsyn/component-argocd.git",
        "github.com/projectsyn/component-argocd.git",
    ),
    (
        "file:///tmp/path/to/repo.git",
        "tmp/path/to/repo.git",
    ),
]


@pytest.mark.parametrize("repo_url,expected", CASES)
def test_dependency_dir(tmp_path: Path, repo_url: str, expected: str):
    path = multi_dependency.dependency_dir(tmp_path, repo_url)
    repos_dir = tmp_path / ".repos"
    assert path == repos_dir / expected


@pytest.mark.parametrize("repo_url,expected", CASES)
def test_dependency_key(tmp_path: Path, repo_url: str, expected: str):
    depkey = multi_dependency.dependency_key(repo_url)
    assert depkey == expected


def test_multi_dependency_init(tmp_path: Path):
    repo_url, ri = setup_remote(tmp_path)
    _ = multi_dependency.MultiDependency(repo_url, tmp_path)

    repo_url_parts = deconstruct_url(repo_url)
    print(repo_url, repo_url_parts)
    bare_clone_path = (
        tmp_path / ".repos" / repo_url_parts.host / repo_url_parts.path[1:]
    )

    assert bare_clone_path.is_dir()
    # Smoke test that the directory is actually a bare clone
    assert (bare_clone_path / "config").exists()
    assert (bare_clone_path / "HEAD").exists()

    b = Repo.init(bare_clone_path)
    assert b.bare
    assert b.working_tree_dir is None


def test_multi_dependency_register_component(tmp_path: Path):
    repo_url, ri = setup_remote(tmp_path)
    md = multi_dependency.MultiDependency(repo_url, tmp_path)

    assert md.get_component("test-component") is None
    assert md.get_package("test-component") is None

    md.register_component("test-component", tmp_path / "tc")

    assert md.get_component("test-component") == tmp_path / "tc"
    assert md.get_package("test-component") is None

    with pytest.raises(ValueError) as e:
        md.register_component("test-component", tmp_path / "tp2")

    assert str(e.value) == "component test-component already registered"


def test_multi_dependency_register_package(tmp_path: Path):
    repo_url, ri = setup_remote(tmp_path)
    md = multi_dependency.MultiDependency(repo_url, tmp_path)

    assert md.get_component("test-package") is None
    assert md.get_package("test-package") is None

    md.register_package("test-package", tmp_path / "tp")

    assert md.get_component("test-package") is None
    assert md.get_package("test-package") == tmp_path / "tp"

    with pytest.raises(ValueError) as e:
        md.register_package("test-package", tmp_path / "tp2")

    assert str(e.value) == "package test-package already registered"


def test_multi_dependency_deregister(tmp_path: Path):
    repo_url, ri = setup_remote(tmp_path)
    md = multi_dependency.MultiDependency(repo_url, tmp_path)

    assert md.get_component("test") is None
    assert md.get_package("test") is None

    md.register_component("test", tmp_path / "tc")

    assert md.get_component("test") == tmp_path / "tc"
    assert md.get_package("test") is None

    md.register_package("test", tmp_path / "tp")

    assert md.get_component("test") == tmp_path / "tc"
    assert md.get_package("test") == tmp_path / "tp"

    with pytest.raises(ValueError) as e:
        md.deregister_component("foo")

    assert str(e.value) == "can't deregister unknown component foo"

    assert md.get_component("test") == tmp_path / "tc"
    assert md.get_package("test") == tmp_path / "tp"

    with pytest.raises(ValueError) as e:
        md.deregister_package("pkg.test")

    assert str(e.value) == "can't deregister unknown package pkg.test"

    assert md.get_component("test") == tmp_path / "tc"
    assert md.get_package("test") == tmp_path / "tp"

    md.deregister_component("test")

    assert md.get_component("test") is None
    assert md.get_package("test") == tmp_path / "tp"

    md.deregister_package("test")

    assert md.get_component("test") is None
    assert md.get_package("test") is None


def test_multi_dependency_checkout_component_exc(tmp_path: Path):
    repo_url, ri = setup_remote(tmp_path)
    md = multi_dependency.MultiDependency(repo_url, tmp_path)

    with pytest.raises(ValueError) as e:
        md.checkout_component("test", "master")

    assert "can't checkout unknown component test" in str(e.value)


def test_multi_dependency_checkout_component(tmp_path: Path):
    repo_url, ri = setup_remote(tmp_path)
    md = multi_dependency.MultiDependency(repo_url, tmp_path)

    target_dir = tmp_path / "test"
    assert not target_dir.is_dir()

    md.register_component("test", target_dir)
    md.checkout_component("test", "master")

    assert target_dir.is_dir()
    assert (target_dir / ".git").is_file()
    assert (target_dir / "test.txt").is_file()

    test = Repo.init(target_dir)
    assert not test.head.is_detached
    assert test.head.commit.hexsha == ri.commit_shas["master"]


def test_multi_dependency_checkout_package_exc(tmp_path: Path):
    repo_url, ri = setup_remote(tmp_path)
    md = multi_dependency.MultiDependency(repo_url, tmp_path)

    with pytest.raises(ValueError) as e:
        md.checkout_package("test", "master")

    assert "can't checkout unknown package test" in str(e.value)


def test_multi_dependency_checkout_package(tmp_path: Path):
    repo_url, ri = setup_remote(tmp_path)
    md = multi_dependency.MultiDependency(repo_url, tmp_path)

    target_dir = tmp_path / "test"
    assert not target_dir.is_dir()

    md.register_package("test", target_dir)
    md.checkout_package("test", "master")

    assert target_dir.is_dir()
    assert (target_dir / ".git").is_file()
    assert (target_dir / "test.txt").is_file()

    test = Repo.init(target_dir)
    assert not test.head.is_detached
    assert test.head.commit.hexsha == ri.commit_shas["master"]


@pytest.mark.parametrize(
    "versions",
    [
        {"component": "master", "package": "test-branch"},
        {"component": "master", "package": "master"},
    ],
)
def test_multi_dependency_checkout_multiple(tmp_path: Path, versions: dict[str, str]):
    repo_url, ri = setup_remote(tmp_path)
    md = multi_dependency.MultiDependency(repo_url, tmp_path)

    component_dir = tmp_path / "test-component"
    package_dir = tmp_path / "test-package"
    assert not component_dir.is_dir()
    assert not package_dir.is_dir()

    md.register_component("test", component_dir)
    md.register_package("test", package_dir)

    md.checkout_component("test", versions["component"])

    assert component_dir.is_dir()
    assert (component_dir / ".git").is_file()
    assert (component_dir / "test.txt").is_file()
    assert not (component_dir / "branch.txt").exists()
    assert not package_dir.is_dir()

    cr = Repo.init(component_dir)
    assert not cr.head.is_detached
    assert cr.head.commit.hexsha == ri.commit_shas[versions["component"]]

    md.checkout_package("test", versions["package"])

    # Verify that component checkout hasn't changed
    assert component_dir.is_dir()
    assert (component_dir / ".git").is_file()
    assert (component_dir / "test.txt").is_file()
    assert not (component_dir / "branch.txt").exists()
    assert not cr.head.is_detached
    assert cr.head.commit.hexsha == ri.commit_shas[versions["component"]]

    # Verify that package checkout exists now
    assert package_dir.is_dir()
    assert (package_dir / ".git").is_file()
    assert (package_dir / "test.txt").is_file()
    if versions["package"] == "test-branch":
        assert (package_dir / "branch.txt").is_file()
    else:
        assert not (package_dir / "branch.txt").exists()

    pr = Repo.init(package_dir)
    assert not pr.head.is_detached
    assert pr.head.commit.hexsha == ri.commit_shas[versions["package"]]
