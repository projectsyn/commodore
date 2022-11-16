from __future__ import annotations

import json
import shutil

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
from commodore.config import Config
from commodore.gitrepo import RefError
from commodore.inventory import Inventory
from commodore.multi_dependency import MultiDependency

from conftest import MockMultiDependency


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
    dep = MultiDependency(repo_url, tmp_path)
    return Component(
        name,
        dependency=dep,
        directory=tmp_path / name,
        version=version,
    )


def _setup_existing_component(tmp_path: P, worktree=True):
    cr = Repo.init(tmp_path / ".repo", bare=True)
    upstream = tmp_path / "upstream"
    u = cr.clone(upstream)
    with open(upstream / "README.md", "w") as f:
        f.write("# Dummy component\n")

    u.index.add(["README.md"])
    u.index.commit("Initial commit")
    u.remote().push()

    # Setup w
    if worktree:
        cr.git.execute(
            ["git", "worktree", "add", "-f", str(tmp_path / "component"), "master"]
        )

    return cr


def test_component_init(tmp_path):
    c = _setup_component(tmp_path)

    assert c.repo_url == REPO_URL

    dep = c.dependency
    assert dep.url == REPO_URL
    assert dep.get_component("argocd") == c.repo_directory


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
        c.dependency = MultiDependency(local_url, tmp_path)
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
    cr = _setup_existing_component(tmp_path)
    cr.create_remote("origin", orig_url)
    dep = MockMultiDependency(cr)

    c = Component(cn, dependency=dep, directory=tmp_path / "component")

    for url in c.repo.repo.remote().urls:
        assert url == orig_url


def _setup_render_jsonnetfile_json(tmp_path: P) -> Component:
    cr = Repo.init(tmp_path / "repo.git", bare=True)
    upath = tmp_path / "upstream"
    ur = cr.clone(upath)
    jsonnetfile = upath / "jsonnetfile.jsonnet"
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
    ur.index.add("*")
    ur.index.commit("initial commit")
    ur.remote().push()

    cdep = MockMultiDependency(cr)
    c = Component(
        "kube-monitoring",
        dependency=cdep,
        directory=tmp_path / "component",
        version="master",
    )
    c.checkout()
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
    print(c.target_directory, c.repo_directory)
    cpath = c.target_directory
    assert (cpath / "jsonnetfile.json").is_file()
    assert _render_jsonnetfile_json_error_string(c) not in stdout
    with open(cpath / "jsonnetfile.json") as jf:
        jsonnetfile_contents = json.load(jf)
        assert isinstance(jsonnetfile_contents, dict)
        # check expected keys are there using set comparison
        assert {"version", "dependencies", "legacyImports"} <= set(
            jsonnetfile_contents.keys()
        )
        assert jsonnetfile_contents["version"] == 1
        assert jsonnetfile_contents["legacyImports"]
        assert jsonnetfile_contents["dependencies"][0]["version"] == "1.18"


@pytest.mark.parametrize("has_repo", [False, True])
def test_render_jsonnetfile_json_warning(tmp_path: P, capsys, has_repo: bool):
    c = _setup_render_jsonnetfile_json(tmp_path)
    if not has_repo:
        shutil.rmtree(c.target_directory / ".git")

    with open(c.target_directory / "jsonnetfile.json", "w") as jf:
        jf.write("{}")
    if has_repo:
        c.repo.repo.index.add("*")
        c.repo.repo.index.commit("Add jsonnetfile.json")

    c.render_jsonnetfile_json(
        {"jsonnetfile_parameters": {"kube_prometheus_version": "1.18"}}
    )

    if has_repo:
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


def test_component_no_dep_get_dependency(tmp_path: P):
    c = Component("test-component", None, directory=tmp_path)
    with pytest.raises(ValueError) as e:
        _ = c.dependency

    assert (
        str(e.value)
        == "Dependency for component test-component hasn't been initialized"
    )


def test_component_no_dep_get_url(tmp_path: P):
    c = Component("test-component", None, directory=tmp_path)
    with pytest.raises(ValueError) as e:
        _ = c.repo_url

    assert (
        str(e.value)
        == "Dependency for component test-component hasn't been initialized"
    )


def test_component_no_dep_checkout(tmp_path: P):
    c = Component("test-component", None, directory=tmp_path)
    with pytest.raises(ValueError) as e:
        c.checkout()

    assert (
        str(e.value)
        == "Dependency for component test-component hasn't been initialized"
    )


@pytest.mark.parametrize("init_dep", [False, True])
@pytest.mark.parametrize("new_dep", [False, True])
def test_component_update_dependency(tmp_path: P, init_dep: bool, new_dep: bool):
    r1 = _setup_existing_component(tmp_path / "tc1")
    r2 = _setup_existing_component(tmp_path / "tc2")

    idep = None
    if init_dep:
        idep = MultiDependency(f"file://{r1.common_dir}", tmp_path / "dependencies")

    c = Component("tc1", idep, tmp_path)

    if init_dep:
        c.checkout()
        assert c.dependency == idep
        assert c.repo_url == idep.url
        assert c.repo.repo.head.commit.hexsha == r1.head.commit.hexsha
    else:
        with pytest.raises(ValueError) as exc:
            _ = c.dependency
        assert str(exc.value) == "Dependency for component tc1 hasn't been initialized"

    ndep = None
    if new_dep:
        ndep = MultiDependency(f"file://{r2.common_dir}", tmp_path / "dependencies")

    c.dependency = ndep

    if ndep:
        c.checkout()
        assert c.dependency == ndep
        assert c.repo_url == ndep.url
        assert c.repo.repo.head.commit.hexsha == r2.head.commit.hexsha
    else:
        with pytest.raises(ValueError) as exc:
            _ = c.dependency
        assert str(exc.value) == "Dependency for component tc1 hasn't been initialized"


@pytest.mark.parametrize("dep", [True, False])
def test_component_repo(tmp_path: P, dep: bool):
    u = Repo.init(tmp_path / "bare.git")
    (tmp_path / "bare.git" / "x").touch()
    u.index.add(["x"])
    u.index.commit("Initial commit")

    if dep:
        md = MultiDependency(f"file://{tmp_path}/bare.git", tmp_path)
    else:
        md = None

    c = Component(
        "test-component", md, directory=tmp_path / "test-component", version="master"
    )
    if md:
        c.checkout()

    assert c.repo.working_tree_dir == tmp_path / "test-component"


def test_component_clone(tmp_path: P, config: Config):
    rem = _setup_existing_component(tmp_path, worktree=False)
    clone_url = f"file://{rem.common_dir}"

    c = Component.clone(config, clone_url, "test-component")

    assert c.repo.repo.head.commit.hexsha == rem.head.commit.hexsha
    assert c.target_directory == tmp_path / "dependencies" / "test-component"
    assert c.target_directory == c.target_dir
    assert c.dependency == config.register_dependency_repo(clone_url)


def test_checkout_is_dirty(tmp_path: P, config: Config):
    rem = _setup_existing_component(tmp_path, worktree=False)
    clone_url = f"file://{rem.common_dir}"

    c = Component.clone(config, clone_url, "test-component")
    c.checkout()
    c._dependency = None

    assert not c.checkout_is_dirty()
