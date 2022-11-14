"""
Unit-tests for git
"""
from __future__ import annotations

import re
import subprocess

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Optional

import os
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
    repo: git.Repo


def setup_remote(tmp_path: Path):
    # Prepare minimum component directories
    remote = tmp_path / "remote.git"
    repo = git.Repo.init(remote)

    (remote / "test.txt").touch(exist_ok=True)

    # setup .gitignore
    with open(remote / ".gitignore", "w", encoding="utf-8") as f:
        f.write("/ignored.txt\n")

    repo.index.add(["test.txt", ".gitignore"])
    commit = repo.index.commit("initial commit")

    (remote / "branch.txt").touch(exist_ok=True)
    repo.index.add(["branch.txt"])
    b = repo.create_head("test-branch")
    b.checkout()
    bc = repo.index.commit("branch")
    repo.create_tag("v1.0.0", ref="master")
    m = [h for h in repo.heads if h.name == "master"][0]
    m.checkout()

    ri = RepoInfo(
        ["master", "test-branch"],
        {"master": commit.hexsha, "test-branch": bc.hexsha},
        repo,
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


def test_gitrepo_init_worktree(tmp_path):
    repo_path = tmp_path / "repo.git"
    r = gitrepo.GitRepo(
        "ssh://git@git.example.com/repo.git",
        repo_path,
        author_name="John Doe",
        author_email="john.doe@example.com",
        bare=True,
    )
    r.initialize_worktree(tmp_path / "repo")

    assert r.repo.head.commit.author.name == "John Doe"
    assert r.repo.head.commit.author.email == "john.doe@example.com"


def test_gitrepo_commit_amend(tmp_path: Path):
    r, ri = setup_repo(tmp_path)
    r._author = git.Actor("John Doe", "john.doe@example.com")

    r.commit("Amended", amend=True)

    assert r.repo.head.commit.message == "Amended\n"
    assert r.repo.head.commit.author.name == "John Doe"
    assert r.repo.head.commit.author.email == "john.doe@example.com"
    assert r.repo.head.commit.committer.name == "John Doe"
    assert r.repo.head.commit.committer.email == "john.doe@example.com"


def _setup_merge_conflict(tmp_path: Path):
    r, _ = setup_repo(tmp_path)
    test_txt_path = r.working_tree_dir / "test.txt"
    with open(test_txt_path, "w", encoding="utf-8") as f:
        f.write("Hello, world!\n")
    r.stage_all()
    r.commit("Add content to test.txt")
    assert not r.repo.is_dirty()

    diff = """diff --git a/test.txt b/test.txt
new file mode 100644
index 0000000..d56c457
--- /dev/null
+++ b/test.txt
@@ -0,0 +1 @@
+Yo World!
"""

    result = subprocess.run(
        ["git", "apply", "-3"], input=diff.encode(), cwd=r.working_tree_dir
    )
    # patch should not apply
    assert result.returncode == 1

    return r


def test_gitrepo_stage_all_raises_on_conflict(tmp_path: Path):
    r = _setup_merge_conflict(tmp_path)

    with pytest.raises(gitrepo.MergeConflict) as e:
        r.stage_all()

    assert str(e.value) == "test.txt"


def test_gitrepo_stage_files_raises_on_conflict(tmp_path: Path):
    r = _setup_merge_conflict(tmp_path)

    with pytest.raises(gitrepo.MergeConflict) as e:
        r.stage_files(["test.txt"])

    assert str(e.value) == "test.txt"


@pytest.mark.parametrize("add_file", [True, False])
@pytest.mark.parametrize("add_ignored_file", [True, False])
@pytest.mark.parametrize(
    "copy_file,convert_to_symlink,remove_file",
    [
        (False, False, False),  # none
        (True, False, False),  # copy test.txt to test2.txt
        (True, True, False),  # change test.txt to a symlink to test2.txt
        (True, False, True),  # copy test.txt to test2.txt and remove test.txt
    ],
)
def test_gitrepo_stage_all(
    tmp_path: Path,
    add_file: bool,
    add_ignored_file: bool,
    copy_file: bool,
    convert_to_symlink: bool,
    remove_file: bool,
):
    r, _ = setup_repo(tmp_path)
    # Initial state of repo: empty file test.txt 0664.

    if add_file:
        with open(r.working_tree_dir / "bar.txt", "w", encoding="utf-8") as f:
            f.write("hello\n")

    if add_file:
        with open(r.working_tree_dir / "ignored.txt", "w", encoding="utf-8") as f:
            f.write("foo\n")

    if copy_file:
        (r.working_tree_dir / "test2.txt").touch()

    if convert_to_symlink:
        assert copy_file
        os.unlink(r.working_tree_dir / "test.txt")
        os.symlink(r.working_tree_dir / "test2.txt", r.working_tree_dir / "test.txt")

    if remove_file:
        os.unlink(r.working_tree_dir / "test.txt")

    diff, changed = r.stage_all()

    assert "ignored.txt" not in diff

    r.commit("Test")

    assert not r.repo.untracked_files
    assert not r.repo.is_dirty()

    committed_paths = list(b[1].path for b in r.repo.index.iter_blobs())

    assert "ignored.txt" not in committed_paths
    assert ("bar.txt" in committed_paths) == add_file
    assert ("test.txt" not in committed_paths) == remove_file
    assert ("test2.txt" in committed_paths) == copy_file


def test_gitrepo_stage_all_ignore_patterns(tmp_path: Path):
    r, _ = setup_repo(tmp_path)

    with open(r.working_tree_dir / "foo.txt", "w", encoding="utf-8") as f:
        f.write("hello\n")

    with open(r.working_tree_dir / "bar.txt", "w", encoding="utf-8") as f:
        f.write("world\n")

    (r.working_tree_dir / "sub").mkdir()
    with open(r.working_tree_dir / "sub" / "bar.txt", "w", encoding="utf-8") as f:
        f.write("world\n")

    r.stage_all(ignore_pattern=re.compile("bar.txt$"))
    r.commit("Update")

    committed_paths = list(b[1].path for b in r.repo.index.iter_blobs())
    assert "foo.txt" in committed_paths
    assert "bar.txt" not in committed_paths
    assert "sub/bar.txt" not in committed_paths


@pytest.mark.parametrize("version", ["master", "v1.0.0"])
def test_gitrepo_is_ahead_of_remote_simple(tmp_path: Path, version: str):
    repo_url, ri = setup_remote(tmp_path)

    r = gitrepo.GitRepo(repo_url, tmp_path / "repo")
    r.checkout(version=version)

    assert not r.is_ahead_of_remote()
    assert r.repo.head.is_detached == (version == "v1.0.0")


def test_gitrepo_is_ahead_of_remote_behind(tmp_path: Path):
    repo_url, ri = setup_remote(tmp_path)
    remote = ri.repo

    r = gitrepo.GitRepo(repo_url, tmp_path / "repo")
    r.checkout(version="master")

    # create new commit in remote and fetch changes
    (Path(remote.working_tree_dir) / "foo.txt").touch()
    remote.index.add(["foo.txt"])
    remote.index.commit("Add foo")

    r.fetch()

    assert not r.is_ahead_of_remote()
    assert len(list(r.repo.iter_commits("master..origin/master"))) == 1


def test_gitrepo_is_ahead_no_remote(tmp_path: Path):
    r = gitrepo.GitRepo(None, tmp_path / "repo", force_init=True)
    (Path(r.working_tree_dir) / "test.txt").touch()
    r.stage_all()
    r.commit("Initial")

    assert len(r.repo.remotes) == 0
    assert not r.is_ahead_of_remote()


def test_gitrepo_is_ahead_of_remote_local_branch(tmp_path: Path):
    repo_url, ri = setup_remote(tmp_path)

    r = gitrepo.GitRepo(repo_url, tmp_path / "repo")
    r.checkout()

    b = r.repo.create_head("local")
    b.checkout()

    (Path(r.working_tree_dir) / "foo.txt").touch()
    r.stage_all()
    r.commit("Add foo.txt")

    assert not r.is_ahead_of_remote()
    # verify that our local branch is ahead of both local and remote tracking master
    assert len(list(r.repo.iter_commits("master..local"))) == 1
    assert len(list(r.repo.iter_commits("origin/master..local"))) == 1
