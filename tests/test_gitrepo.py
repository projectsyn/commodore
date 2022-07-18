"""
Unit-tests for git
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Optional

import shutil

import click
import git
import pytest

from commodore import gitrepo
from pathlib import Path


@dataclass
class RepoInfo:
    branches: Iterable[str]
    commit_shas: dict[str, str]


def setup_remote(tmp_path: Path):
    # Prepare minimum component directories
    remote = tmp_path / "remote.git"
    repo = git.Repo.init(remote)

    (remote / "test.txt").touch(exist_ok=True)

    repo.index.add(["test.txt"])
    commit = repo.index.commit("initial commit")

    (remote / "branch.txt").touch(exist_ok=True)
    repo.index.add(["branch.txt"])
    b = repo.create_head("test-branch")
    b.checkout()
    bc = repo.index.commit("branch")
    repo.create_tag("v1.0.0", ref="master")
    repo.head.set_reference("master")
    repo.index.checkout()

    ri = RepoInfo(
        ["master", "test-branch"],
        {"master": commit.hexsha, "test-branch": bc.hexsha},
    )

    return f"file://{remote.absolute()}", ri


def setup_repo(tmp_path: Path, repo_url: Optional[str] = None):
    ri = None
    if not repo_url:
        repo_url, ri = setup_remote(tmp_path)
    r = gitrepo.GitRepo(repo_url, tmp_path / "local", force_init=True)
    r.checkout()
    return r, ri


def test_gitrepo_clone_error(tmp_path: Path):
    inexistent_url = "ssh://git@git.example.com/some/repo.git"
    with pytest.raises(click.ClickException) as excinfo:
        gitrepo.GitRepo.clone(inexistent_url, tmp_path, None)
    assert inexistent_url in str(excinfo.value)


def test_gitrepo_clone_initial_commit(tmp_path: Path):
    git.Repo.init(tmp_path / "repo.git")
    url = f"file:///{tmp_path}/repo.git"

    r = gitrepo.GitRepo.clone(url, tmp_path / "repo", None)

    assert r.repo.head
    assert r.repo.working_tree_dir
    assert r.repo.head.commit.message == "Initial commit"


def test_gitrepo_update_remote(tmp_path: Path):
    new_url = "ssh://git@git.example.com/some/repo.git"
    repo = gitrepo.GitRepo(None, tmp_path, force_init=True)
    repo.remote = new_url
    assert repo.repo.remotes.origin.url == new_url


def test_gitrepo_remote(tmp_path: Path):
    repo_url = "ssh://user@host/path/to/repo.git"
    r = gitrepo.GitRepo(repo_url, tmp_path, force_init=True)

    assert r.remote == repo_url
    assert r.repo.git.remote("get-url", "origin") == repo_url


@pytest.mark.parametrize(
    "repo_url",
    [
        "ssh://user@host/path/to/repo.git",
        "file:///path/to/repo.git",
    ],
)
@pytest.mark.parametrize("init", [True, False])
def test_gitrepo_remote_no_push_substitution(tmp_path: Path, repo_url: str, init):
    """Test that push URLs are not substituted for non-HTTP(S) remote URLs."""
    if init:
        r = gitrepo.GitRepo(repo_url, tmp_path, force_init=True)
    else:
        r = gitrepo.GitRepo(None, tmp_path, force_init=True)
        r.remote = repo_url

    pull_remote = r.repo.git.remote("get-url", "origin")
    push_remote = r.repo.git.remote("get-url", "--push", "origin")
    assert pull_remote == repo_url
    assert push_remote == repo_url


@pytest.mark.parametrize("init", [True, False])
@pytest.mark.parametrize(
    "repo_url,normalized_url",
    [
        ("user@host:path/to/repo.git", "ssh://user@host/path/to/repo.git"),
        ("ssh://user@host///path/to/repo.git", "ssh://user@host/path/to/repo.git"),
        (
            "ssh://user@host:2222/path////to/repo.git",
            "ssh://user@host:2222/path/to/repo.git",
        ),
    ],
)
def test_gitrepo_remote_normalize(tmp_path, init, repo_url, normalized_url):
    """Test that ssh remotes are normalized to their
    ssh://user@host[:port]/... form"""
    if init:
        r = gitrepo.GitRepo(repo_url, tmp_path, force_init=True)
    else:
        r = gitrepo.GitRepo(None, tmp_path, force_init=True)
        r.remote = repo_url

    pull_remote = r.repo.git.remote("get-url", "origin")
    push_remote = r.repo.git.remote("get-url", "--push", "origin")
    assert pull_remote == normalized_url
    assert push_remote == normalized_url


@pytest.mark.parametrize(
    "repo_url,push_url",
    [
        ("http://host/path/to/repo.git", "ssh://git@host/path/to/repo.git"),
        ("https://host/path/to/repo.git", "ssh://git@host/path/to/repo.git"),
        ("https://host:1234/path/to/repo.git", "ssh://git@host/path/to/repo.git"),
        ("https://user@host/path/to/repo.git", "ssh://git@host/path/to/repo.git"),
        ("https://user:pass@host/path/to/repo.git", "ssh://git@host/path/to/repo.git"),
        (
            "https://user:pass@host:1234/path/to/repo.git",
            "ssh://git@host/path/to/repo.git",
        ),
    ],
)
@pytest.mark.parametrize("init", [True, False])
def test_gitrepo_remote_push_substitution(tmp_path, repo_url, push_url, init):
    """Test that push URLs get substituted for common patterns."""
    if init:
        r = gitrepo.GitRepo(repo_url, tmp_path, force_init=True)
    else:
        r = gitrepo.GitRepo(None, tmp_path, force_init=True)
        r.remote = repo_url

    pull_remote = r.remote
    push_remote = r.repo.git.remote("get-url", "--push", "origin")
    assert pull_remote == repo_url
    assert push_remote == push_url


def test_gitrepo_working_tree_dir(tmp_path: Path):
    r, _ = setup_repo(tmp_path)

    assert r.working_tree_dir
    assert r.working_tree_dir == tmp_path / "local"


def test_gitrepo_head_short_sha(tmp_path: Path):
    r, ri = setup_repo(tmp_path)

    short_len = len(r.head_short_sha)
    assert r.head_short_sha == ri.commit_shas["master"][:short_len]


def test_gitrepo_reset(tmp_path: Path):
    r, _ = setup_repo(tmp_path)

    testf = r.working_tree_dir / "test.txt"
    with open(testf, "w") as f:
        f.write("Hello, world!\n")
    assert r.repo.is_dirty()

    r.reset(working_tree=True)

    assert not r.repo.is_dirty()


def test_gitrepo_push_empty_remote(tmp_path: Path):
    git.Repo.init(tmp_path / "remote.git", mkdir=True, bare=True)
    r = gitrepo.GitRepo(
        f"file:///{tmp_path}/remote.git", tmp_path / "local", force_init=True
    )

    testf = r.working_tree_dir / "test.txt"
    with open(testf, "w") as f:
        f.write("Hello, world!\n")
    r.stage_all()
    r.commit("Initial commit")
    r.push()


def test_gitrepo_checkout_branch(tmp_path: Path):
    branch = "test-branch"
    r, ri = setup_repo(tmp_path)
    assert branch in ri.branches

    r.checkout(branch)

    repo = r.repo
    assert repo.head.ref.name == branch
    for rb in repo.remote().refs:
        if rb.name.endswith(branch):
            remote_branch_commit = rb.commit
            break
    else:
        raise ValueError(f"No remote branch for {branch}")

    assert not repo.head.is_detached
    assert repo.head.ref.name == branch
    assert repo.head.commit.hexsha == ri.commit_shas[branch]
    assert repo.head.commit == remote_branch_commit


def test_gitrepo_checkout_sha1version(tmp_path: Path):
    r, ri = setup_repo(tmp_path)
    commit = ri.commit_shas["master"]

    r.checkout(commit)

    assert r.repo.head.is_detached
    assert r.repo.head.commit.hexsha == commit


def test_gitrepo_checkout_tag(tmp_path: Path):
    r, ri = setup_repo(tmp_path)

    r.checkout("v1.0.0")

    assert r.repo.head.is_detached
    assert r.repo.head.commit.hexsha == r.repo.tags["v1.0.0"].commit.hexsha


def test_gitrepo_checkout_nonexisting_version(tmp_path: Path):
    r, _ = setup_repo(tmp_path)

    with pytest.raises(gitrepo.RefError):
        r.checkout("does-not-exist")


def test_gitrepo_checkout_existing_repo_update_version_branch(tmp_path: Path):
    r, _ = setup_repo(tmp_path)
    r.checkout()

    assert not r.repo.head.is_detached
    assert r.repo.head.ref.name == "master"

    # checkout branch
    branch = "test-branch"
    r.checkout(branch)

    assert not r.repo.head.is_detached
    assert r.repo.head.ref.name == branch


def test_gitrepo_checkout_existing_repo_update_version_sha1version(tmp_path: Path):
    r, ri = setup_repo(tmp_path)
    r.checkout()

    assert not r.repo.head.is_detached
    assert r.repo.head.ref.name == "master"

    # update version
    r.checkout(ri.commit_shas["test-branch"])

    assert r.repo.head.is_detached
    assert r.repo.head.commit.hexsha == ri.commit_shas["test-branch"]


def test_gitrepo_checkout_existing_repo_update_latest_upstream(tmp_path: Path):
    r, ri = setup_repo(tmp_path)
    r.checkout("test-branch")

    assert not r.repo.head.is_detached
    assert r.repo.head.ref.name == "test-branch"
    head_commit = r.repo.head.commit.hexsha
    assert head_commit == ri.commit_shas["test-branch"]

    r.repo.git.reset("HEAD^", hard=True)

    assert not r.repo.head.is_detached
    assert r.repo.head.ref.name == "test-branch"
    assert r.repo.head.commit.hexsha != head_commit
    assert r.repo.head.commit.hexsha == ri.commit_shas["master"]

    r.checkout("test-branch")

    assert not r.repo.head.is_detached
    assert r.repo.head.ref.name == "test-branch"
    assert r.repo.head.commit.hexsha == head_commit
    assert not r.repo.is_dirty()


@pytest.mark.parametrize(
    "mode",
    ["reinit", "update"],
)
def test_gitrepo_checkout_existing_repo_update_remote(tmp_path: Path, mode: str):
    r, _ = setup_repo(tmp_path)
    r.checkout()

    assert not r.repo.head.is_detached
    assert r.repo.head.ref.name == "master"

    # remember original url of remote origin
    orig_url = next(r.repo.remote().urls)
    # create local upstream repo
    local = tmp_path / "upstream" / "argocd.git"
    git.Repo.init(local, bare=True)
    local_url = f"file://{local}"
    local_ver = "local-branch"

    # push repo to local upstream with a custom branch
    r.repo.create_remote("local", local_url)
    r.repo.create_head(local_ver)
    r.repo.remote("local").push(local_ver)
    r.repo.delete_remote("local")
    r.repo.delete_head(local_ver)

    if mode == "reinit":
        # reinitialize component object on existing repo with different url/version info
        r, _ = setup_repo(tmp_path, repo_url=local_url)
        r.checkout(local_ver)
    elif mode == "update":
        r.remote = local_url
        r.checkout(local_ver)
    else:
        raise ValueError(f"Unknown mode {mode} for test")

    assert local_url in r.repo.remote().urls
    assert orig_url not in r.repo.remote().urls
    assert not r.repo.head.is_detached
    assert r.repo.head.ref.name == "local-branch"


def test_gitrepo_checkout_bare(tmp_path: Path):
    repo_url, ri = setup_remote(tmp_path)
    r = gitrepo.GitRepo(repo_url, targetdir=tmp_path / "bare.git", bare=True)

    assert (tmp_path / "bare.git" / "config").is_file()
    assert (tmp_path / "bare.git" / "HEAD").is_file()

    assert r.repo.bare


def test_gitrepo_checkout_worktree(tmp_path: Path):
    repo_url, ri = setup_remote(tmp_path)
    r = gitrepo.GitRepo(repo_url, targetdir=tmp_path / "bare.git", bare=True)

    r.checkout_worktree(tmp_path / "repo", "master")

    wtr = git.Repo.init(tmp_path / "repo")
    assert not wtr.bare
    assert not wtr.head.is_detached
    assert wtr.head.ref.name == "master"
    assert wtr.head.commit.hexsha == ri.commit_shas["master"]


def test_gitrepo_checkout_worktree_update_version(tmp_path: Path):
    repo_url, ri = setup_remote(tmp_path)
    r = gitrepo.GitRepo(repo_url, targetdir=tmp_path / "bare.git", bare=True)

    worktree = tmp_path / "repo"
    r.checkout_worktree(worktree, "master")

    wtr = git.Repo.init(worktree)
    assert not wtr.bare
    assert not wtr.head.is_detached
    assert wtr.head.ref.name == "master"
    assert wtr.head.commit.hexsha == ri.commit_shas["master"]

    r.checkout_worktree(worktree, "test-branch")
    assert not wtr.bare
    assert not wtr.head.is_detached
    assert wtr.head.ref.name == "test-branch"
    assert wtr.head.commit.hexsha == ri.commit_shas["test-branch"]


def test_gitrepo_checkout_worktree_update_remote(tmp_path: Path):
    repo_url_1, ri1 = setup_remote(tmp_path / "remote1")
    repo_url_2, ri2 = setup_remote(tmp_path / "remote2")

    r1 = gitrepo.GitRepo(repo_url_1, targetdir=tmp_path / "bare.git", bare=True)

    worktree = tmp_path / "repo"
    r1.checkout_worktree(worktree, "master")

    wtr1 = git.Repo.init(worktree)
    assert not wtr1.bare
    assert not wtr1.head.is_detached
    assert wtr1.head.ref.name == "master"
    assert wtr1.head.commit.hexsha == ri1.commit_shas["master"]

    r2 = gitrepo.GitRepo(repo_url_2, targetdir=tmp_path / "bare-2.git", bare=True)

    r2.checkout_worktree(worktree, "master")

    wtr2 = git.Repo.init(worktree)
    assert not wtr2.bare
    assert not wtr2.head.is_detached
    assert wtr2.head.ref.name == "master"
    assert wtr2.head.commit.hexsha == ri2.commit_shas["master"]


def test_gitrepo_checkout_worktree_update_remote_abort(tmp_path: Path):
    repo_url_1, ri1 = setup_remote(tmp_path / "remote1")
    repo_url_2, ri2 = setup_remote(tmp_path / "remote2")

    r1 = gitrepo.GitRepo(repo_url_1, targetdir=tmp_path / "bare.git", bare=True)
    r2 = gitrepo.GitRepo(repo_url_2, targetdir=tmp_path / "bare-2.git", bare=True)

    worktree = tmp_path / "repo"
    r1.checkout_worktree(worktree, "master")

    wtr = git.Repo.init(worktree)
    assert not wtr.bare
    assert not wtr.head.is_detached
    assert wtr.head.ref.name == "master"
    assert wtr.head.commit.hexsha == ri1.commit_shas["master"]

    (worktree / "u.txt").touch()

    with pytest.raises(click.ClickException) as e:
        r2.checkout_worktree(worktree, "master")

    assert f"Switching remote for worktree '{worktree.resolve()}'" in str(e.value)


def test_gitrepo_checkout_worktree_migrate(tmp_path: Path):
    repo_url, ri = setup_remote(tmp_path)
    bare_repo = gitrepo.GitRepo(repo_url, targetdir=tmp_path / "bare.git", bare=True)

    repo_dir = tmp_path / "repo"
    old_repo = gitrepo.GitRepo(repo_url, targetdir=repo_dir)
    old_repo.checkout("master")
    assert (repo_dir / ".git").is_dir()

    bare_repo.checkout_worktree(repo_dir, "test-branch")

    wtr = git.Repo.init(repo_dir)
    assert (repo_dir / ".git").is_file()
    assert Path(wtr.common_dir).resolve() == tmp_path / "bare.git"


@pytest.mark.parametrize(
    "change",
    ["untracked file", "dirty file", "local branch"],
)
def test_gitrepo_checkout_worktree_migrate_abort(tmp_path, change):
    repo_url, ri = setup_remote(tmp_path)
    r = gitrepo.GitRepo(repo_url, targetdir=tmp_path / "bare.git", bare=True)

    repo_dir = tmp_path / "repo"
    old_repo = gitrepo.GitRepo(repo_url, targetdir=repo_dir)
    old_repo.checkout("master")
    assert (repo_dir / ".git").is_dir()

    if change == "untracked file":
        (repo_dir / "u.txt").touch()
    elif change == "dirty file":
        with open(repo_dir / "test.txt", "a") as f:
            f.write("testing\n")
    elif change == "local branch":
        old_repo.repo.create_head("local-branch")
    else:
        raise ValueError(f"Test case '{change}' NYI")

    with pytest.raises(click.ClickException) as e:
        r.checkout_worktree(repo_dir, "master")

    assert f"Migrating dependency {repo_dir.resolve()}" in str(e.value)


def test_gitrepo_checkout_worktree_no_remote(tmp_path):
    repo_path = tmp_path / "repo.git"
    u = git.Repo.init(repo_path)
    (repo_path / "test.txt").touch()
    u.index.add(["test.txt"])
    c = u.index.commit("initial commit")

    r = gitrepo.GitRepo(None, repo_path)
    r.checkout_worktree(tmp_path / "worktree", "master")

    w = git.Repo.init(tmp_path / "worktree")
    assert not w.head.is_detached
    assert w.head.commit.hexsha == c.hexsha
    assert w.head.ref.name == "master"
    assert (tmp_path / "worktree" / "test.txt").is_file()


def test_gitrepo_list_worktrees(tmp_path: Path):
    r, ri = setup_repo(tmp_path)

    initial_wts = r.worktrees
    assert len(initial_wts) == 1
    assert initial_wts[0].working_tree_dir == r.working_tree_dir
    assert initial_wts[0].repo.head.commit.hexsha == ri.commit_shas["master"]

    r.checkout_worktree(tmp_path / "worktree", version="test-branch")

    worktrees = r.worktrees
    assert len(worktrees) == 2
    assert worktrees[0].working_tree_dir == initial_wts[0].working_tree_dir
    assert worktrees[1].working_tree_dir == tmp_path / "worktree"
    assert worktrees[1].repo.head.commit.hexsha == ri.commit_shas["test-branch"]

    shutil.rmtree(worktrees[1].working_tree_dir)

    worktrees_after_delete = r.worktrees
    assert len(worktrees_after_delete) == 1
    assert worktrees_after_delete[0].working_tree_dir == r.working_tree_dir
    assert worktrees_after_delete[0].repo.head.commit.hexsha == ri.commit_shas["master"]
