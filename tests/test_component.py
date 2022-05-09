from __future__ import annotations

import json
import pytest
import yaml

from collections.abc import Iterable
from pathlib import Path as P
from git import Repo
from textwrap import dedent


from commodore.component import (
    Component,
    component_dir,
    component_parameters_key,
)
from commodore.gitrepo import RefError
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


REPO_URL = "https://github.com/projectsyn/component-argocd.git"


def _setup_component(
    tmp_path: P,
    version="master",
    repo_url=REPO_URL,
    name="argocd",
):
    return Component(
        name,
        repo_url=repo_url,
        directory=tmp_path / name,
        version=version,
    )


def test_component_checkout(tmp_path):
    c = _setup_component(tmp_path)

    c.checkout()

    assert c.version == "master"
    assert c.repo.repo.head.ref.name == "master"
    pull_remote = c.repo.remote
    push_remote = c.repo.repo.git.remote("get-url", "--push", "origin")
    assert pull_remote == REPO_URL
    assert push_remote.startswith("ssh://git@")
    assert push_remote == REPO_URL.replace("https://", "ssh://git@")


def test_component_checkout_branch(tmp_path):
    branch = "component-defs-in-applications"
    c = _setup_component(tmp_path, version=branch)

    c.checkout()

    assert c.version == branch
    repo = c.repo.repo
    assert repo.head.ref.name == branch
    for rb in repo.remote().refs:
        if rb.name.endswith(branch):
            remote_branch_commit = rb.commit
            break
    else:
        raise ValueError(f"No remote branch for {branch}")

    assert not repo.head.is_detached
    assert repo.head.ref.name == branch
    assert repo.head.commit == remote_branch_commit


def test_component_checkout_sha1version(tmp_path: P):
    commit = "696b4b4cb9a86ebc845daa314a0a98957f89e99b"
    c = _setup_component(tmp_path, version=commit)

    c.checkout()

    assert c.repo.repo.head.is_detached
    assert c.repo.repo.head.commit.hexsha == commit


def test_component_checkout_tag(tmp_path: P):
    c = _setup_component(
        tmp_path,
        version="v1.0.0",
        repo_url="https://github.com/projectsyn/component-backup-k8up.git",
        name="backup-k8up",
    )

    c.checkout()

    assert c.repo.repo.head.is_detached
    assert c.repo.repo.head.commit.hexsha == c.repo.repo.tags["v1.0.0"].commit.hexsha


def test_component_checkout_nonexisting_version(tmp_path: P):
    c = _setup_component(tmp_path, version="does-not-exist")

    with pytest.raises(RefError):
        c.checkout()


def test_component_checkout_existing_repo_update_version_branch(tmp_path: P):
    c = _setup_component(tmp_path, version="master")
    c.checkout()

    assert not c.repo.repo.head.is_detached
    assert c.repo.repo.head.ref.name == "master"

    # update version
    branch = "component-defs-in-applications"
    c.version = branch

    c.checkout()

    assert not c.repo.repo.head.is_detached
    assert c.repo.repo.head.ref.name == branch


def test_component_checkout_existing_repo_update_version_sha1version(tmp_path: P):
    c = _setup_component(tmp_path, version="master")
    c.checkout()

    assert not c.repo.repo.head.is_detached
    assert c.repo.repo.head.ref.name == "master"

    # update version
    commit = "696b4b4cb9a86ebc845daa314a0a98957f89e99b"
    c.version = commit

    c.checkout()

    assert c.repo.repo.head.is_detached
    assert c.repo.repo.head.commit.hexsha == commit


def test_component_checkout_existing_repo_update_latest_upstream(tmp_path: P):
    c = _setup_component(tmp_path, version="master")
    c.checkout()

    assert not c.repo.repo.head.is_detached
    assert c.repo.repo.head.ref.name == "master"
    master_commit = c.repo.repo.head.commit.hexsha

    c.repo.repo.git.reset("HEAD^", hard=True)

    assert not c.repo.repo.head.is_detached
    assert c.repo.repo.head.ref.name == "master"
    assert c.repo.repo.head.commit.hexsha != master_commit

    c.checkout()

    assert not c.repo.repo.head.is_detached
    assert c.repo.repo.head.ref.name == "master"
    assert not c.repo.repo.is_dirty()


@pytest.mark.parametrize(
    "mode",
    ["reinit", "update"],
)
def test_component_checkout_existing_repo_update_remote(tmp_path: P, mode: str):
    c = _setup_component(tmp_path, version="master")
    c.checkout()

    assert not c.repo.repo.head.is_detached
    assert c.repo.repo.head.ref.name == "master"

    # remember original url of remote origin
    orig_url = next(c.repo.repo.remote().urls)
    # create local upstream repo
    local = tmp_path / "upstream" / "argocd.git"
    Repo.init(local, bare=True)
    local_url = f"file://{local}"
    local_ver = "local-branch"

    # push repo to local upstream with a custom branch
    c.repo.repo.create_remote("local", local_url)
    c.repo.repo.create_head(local_ver)
    c.repo.repo.remote("local").push(local_ver)
    c.repo.repo.delete_remote("local")
    c.repo.repo.delete_head(local_ver)

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

    assert local_url in c.repo.repo.remote().urls
    assert orig_url not in c.repo.repo.remote().urls
    assert not c.repo.repo.head.is_detached
    assert c.repo.repo.head.ref.name == "local-branch"


def test_init_existing_component(tmp_path: P):
    cn = "test-component"
    orig_url = "git@github.com:projectsyn/commodore.git"
    setup_directory(tmp_path)
    cr = Repo.init(tmp_path)
    cr.create_remote("origin", orig_url)

    c = Component(cn, directory=tmp_path)

    for url in c.repo.repo.remote().urls:
        assert url == orig_url


def _setup_render_jsonnetfile_json(tmp_path: P) -> Component:
    Repo.init(tmp_path)
    c = Component("kube-monitoring", directory=tmp_path)
    jsonnetfile = tmp_path / "jsonnetfile.jsonnet"
    with open(jsonnetfile, "w") as jf:
        jf.write(
            dedent(
                """
            {
               version: 1,
               dependencies: [
                    {
                        source: {
                            git: {
                                remote: "https://github.com/coreos/kube-prometheus",
                                subdir: "jsonnet/kube-prometheus",
                            },
                        },
                        version: std.extVar("kube_prometheus_version"),
                    },
               ],
               legacyImports: true,
            }"""
            )
        )
    c.repo.repo.index.add("*")
    c.repo.repo.index.commit("Initial commit")
    return c


def _render_jsonnetfile_json_error_string(c: Component):
    return (
        f" > [WARN] Component {c.name} repo contains both jsonnetfile.json and jsonnetfile.jsonnet, "
        + "continuing with jsonnetfile.jsonnet"
    )


def test_render_jsonnetfile_json(tmp_path: P, capsys):
    c = _setup_render_jsonnetfile_json(tmp_path)

    c.render_jsonnetfile_json(
        {"jsonnetfile_parameters": {"kube_prometheus_version": "1.18"}}
    )

    stdout, _ = capsys.readouterr()
    assert (tmp_path / "jsonnetfile.json").is_file()
    assert _render_jsonnetfile_json_error_string(c) not in stdout
    with open(tmp_path / "jsonnetfile.json") as jf:
        jsonnetfile_contents = json.load(jf)
        assert isinstance(jsonnetfile_contents, dict)
        # check expected keys are there using set comparison
        assert {"version", "dependencies", "legacyImports"} <= set(
            jsonnetfile_contents.keys()
        )
        assert jsonnetfile_contents["version"] == 1
        assert jsonnetfile_contents["legacyImports"]
        assert jsonnetfile_contents["dependencies"][0]["version"] == "1.18"


def test_render_jsonnetfile_json_warning(tmp_path: P, capsys):
    c = _setup_render_jsonnetfile_json(tmp_path)
    with open(tmp_path / "jsonnetfile.json", "w") as jf:
        jf.write("{}")
    c.repo.repo.index.add("*")
    c.repo.repo.index.commit("Add jsonnetfile.json")

    c.render_jsonnetfile_json(
        {"jsonnetfile_parameters": {"kube_prometheus_version": "1.18"}}
    )

    stdout, _ = capsys.readouterr()
    assert _render_jsonnetfile_json_error_string(c) in stdout


@pytest.mark.parametrize(
    "name,key",
    [
        ("simple", "simple"),
        ("simple-name", "simple_name"),
        ("some-other-name", "some_other_name"),
    ],
)
def test_component_parameters_key(name: str, key: str):
    assert component_parameters_key(name) == key


def _setup_libfiles(c: Component, libfiles: Iterable[str]):
    lib_dir = c.target_directory / "lib"
    if len(libfiles) > 0:
        lib_dir.mkdir(parents=True, exist_ok=True)
    for libf in libfiles:
        with open(lib_dir / libf, "w") as f:
            yaml.safe_dump({"libf": libf}, f)


@pytest.mark.parametrize(
    "libfiles",
    [
        [],
        ["foo.libsonnet"],
        ["foo.libsonnet", "bar.libsonnet"],
        [".test.libsonnet", "test.libsonnet"],
    ],
)
def test_component_lib_files(tmp_path: P, libfiles: Iterable[str]):
    c = _setup_component(tmp_path, name="tc1")
    _setup_libfiles(c, libfiles)

    assert sorted(c.lib_files) == sorted(
        tmp_path / "tc1" / "lib" / f for f in libfiles if not f.startswith(".")
    )


@pytest.mark.parametrize(
    "libfiles",
    [
        [],
        ["foo.libsonnet"],
        ["foo.libsonnet", "bar.libsonnet"],
    ],
)
def test_component_get_library(tmp_path: P, libfiles: Iterable[str]):
    c = _setup_component(tmp_path, name="tc1")
    _setup_libfiles(c, libfiles)

    if len(libfiles) == 0:
        assert c.get_library("foo.libsonnet") is None

    for f in libfiles:
        assert c.get_library(f) == tmp_path / "tc1" / "lib" / f
