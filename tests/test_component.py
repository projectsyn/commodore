import json
import pytest

from pathlib import Path as P
from git import Repo


from commodore.component import Component, component_dir, RefError
from commodore.inventory import Inventory


def setup_directory(tmp_path: P):
    inv = Inventory(work_dir=tmp_path)
    inv.ensure_dirs()

    jsonnetfile = tmp_path / "jsonnetfile.json"
    with open(jsonnetfile, "w") as jf:
        json.dump({"version": 1, "dependencies": [], "legacyImports": True}, jf)


def _init_repo(tmp_path: P, cn: str, url: str):
    setup_directory(tmp_path)
    cr = Repo.init(component_dir(cn))
    cr.create_remote("origin", url)


def _setup_component(
    tmp_path: P,
    version="master",
    repo_url="https://github.com/projectsyn/component-argocd.git",
):
    return Component(
        "argocd",
        repo_url=repo_url,
        directory=tmp_path / "argocd",
        version=version,
    )


def test_component_checkout(tmp_path):
    c = _setup_component(tmp_path)

    c.checkout()

    assert c.repo.head.ref.name == "master"


def test_component_checkout_branch(tmp_path):
    branch = "component-defs-in-applications"
    c = _setup_component(tmp_path, version=branch)

    c.checkout()

    assert c.repo.head.ref.name == branch
    for rb in c.repo.remote().refs:
        if rb.name.endswith(branch):
            remote_branch_commit = rb.commit
            break
    else:
        raise ValueError(f"No remote branch for {branch}")

    assert c.repo.head.ref.name == branch
    assert c.repo.head.commit == remote_branch_commit


def test_component_checkout_sha1version(tmp_path: P):
    commit = "696b4b4cb9a86ebc845daa314a0a98957f89e99b"
    c = _setup_component(tmp_path, version=commit)

    c.checkout()

    assert c.repo.head.is_detached
    assert c.repo.head.commit.hexsha == commit


def test_component_checkout_nonexisting_version(tmp_path: P):
    c = _setup_component(tmp_path, version="does-not-exist")

    with pytest.raises(RefError):
        c.checkout()


def test_component_checkout_existing_repo_update_version(tmp_path: P):
    c = _setup_component(tmp_path, version="master")
    c.checkout()

    assert not c.repo.head.is_detached
    assert c.repo.head.ref.name == "master"

    # update version
    commit = "696b4b4cb9a86ebc845daa314a0a98957f89e99b"
    c.version = commit

    c.checkout()

    assert c.repo.head.is_detached
    assert c.repo.head.commit.hexsha == commit


@pytest.mark.parametrize(
    "mode",
    ["reinit", "update"],
)
def test_component_checkout_existing_repo_update_remote(tmp_path: P, mode: str):
    c = _setup_component(tmp_path, version="master")
    c.checkout()

    assert not c.repo.head.is_detached
    assert c.repo.head.ref.name == "master"

    # remember original url of remote origin
    orig_url = next(c.repo.remote().urls)
    # create local upstream repo
    local = tmp_path / "upstream" / "argocd.git"
    Repo.init(local, bare=True)
    local_url = f"file://{local}"
    local_ver = "local-branch"

    # push repo to local upstream with a custom branch
    c.repo.create_remote("local", local_url)
    c.repo.create_head(local_ver)
    c.repo.remote("local").push(local_ver)
    c.repo.delete_remote("local")
    c.repo.delete_head(local_ver)

    if mode == "reinit":
        # reinitialize component object on existing repo with different url/version info
        c = _setup_component(tmp_path, version=local_ver, repo_url=local_url)
        c.checkout()
    elif mode == "update":
        c.repo_url = local_url
        c.version = local_ver
        c.checkout()
    else:
        raise ValueError(f"Unknown mode {mode} for test")

    assert local_url in c.repo.remote().urls
    assert orig_url not in c.repo.remote().urls
    assert not c.repo.head.is_detached
    assert c.repo.head.ref.name == "local-branch"


def test_init_existing_component(tmp_path: P):
    cn = "test-component"
    orig_url = "git@github.com:projectsyn/commodore.git"
    setup_directory(tmp_path)
    cr = Repo.init(tmp_path)
    cr.create_remote("origin", orig_url)

    c = Component(cn, directory=tmp_path)

    for url in c.repo.remote().urls:
        assert url == orig_url
