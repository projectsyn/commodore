"""
Unit-tests for git
"""

import click
import git
import pytest

from commodore import gitrepo
from pathlib import Path


def setup_remote(tmp_path: Path):
    # Prepare minimum component directories
    remote = tmp_path / "remote.git"
    repo = git.Repo.init(remote)

    (remote / "test.txt").touch(exist_ok=True)

    repo.index.add(["test.txt"])
    commit = repo.index.commit("initial commit")

    return f"file://{remote.absolute()}", commit.hexsha


def setup_repo(tmp_path: Path):
    repo_url, commit_sha = setup_remote(tmp_path)
    r = gitrepo.GitRepo(repo_url, tmp_path / "local", force_init=True)
    r.checkout()
    return r, commit_sha


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
    r, head_sha = setup_repo(tmp_path)

    short_len = len(r.head_short_sha)
    assert r.head_short_sha == head_sha[:short_len]


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
