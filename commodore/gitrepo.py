from __future__ import annotations

import difflib
import hashlib
import shutil

from collections import namedtuple
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Optional, Protocol

import click

from git import Actor, BadName, FetchInfo, GitCommandError, PushInfo, Repo
from git.objects import Tree

from url_normalize import url_normalize
from url_normalize.tools import deconstruct_url, reconstruct_url


class RefError(ValueError):
    pass


CommitInfo = namedtuple("CommitInfo", ["commit", "branch", "tag"])


class DiffFunc(Protocol):
    def __call__(
        self, before_text: str, after_text: str, fromfile: str = "", tofile: str = ""
    ) -> tuple[Iterable[str], bool]:
        ...


def _normalize_git_ssh(url: str) -> str:
    # Import url_normalize internal methods here, so they're not visible in the file
    # scope of gitrepo.py
    # pylint: disable=import-outside-toplevel
    from url_normalize.url_normalize import (
        normalize_userinfo,
        normalize_host,
        normalize_path,
        provide_url_scheme,
    )

    if "@" in url and not url.startswith("ssh://"):
        # Assume git@host:repo format, reformat so url_normalize understands
        # the URL
        host, repo = url.split(":")
        url = f"{host}/{repo}"
    # Reuse normalization logic from url_normalize, simplify for Git-SSH use case.
    # We can't do `url_normalize(url, "ssh"), because the library doesn't know "ssh" as
    # a scheme, and fails to look up the default port for "ssh".
    url = provide_url_scheme(url, "ssh")
    urlparts = deconstruct_url(url)
    urlparts = urlparts._replace(
        userinfo=normalize_userinfo(urlparts.userinfo),
        host=normalize_host(urlparts.host),
        path=normalize_path(urlparts.path, scheme="https"),
    )
    return reconstruct_url(urlparts)


def normalize_git_url(url: str) -> str:
    """Normalize HTTP(s) and SSH Git URLs"""
    if "@" in url and ("://" not in url or url.startswith("ssh://")):
        url = _normalize_git_ssh(url)
    elif url.startswith("http://") or url.startswith("https://"):
        url = url_normalize(url)
    return url


def _colorize_diff(line: str) -> str:
    if line.startswith("--- ") or line.startswith("+++ ") or line.startswith("@@ "):
        return click.style(line, fg="yellow")
    if line.startswith("+"):
        return click.style(line, fg="green")
    if line.startswith("-"):
        return click.style(line, fg="red")
    return line


def _compute_similarity(change):
    before = change.b_blob.data_stream.read().decode("utf-8").split("\n")
    after = change.a_blob.data_stream.read().decode("utf-8").split("\n")
    r = difflib.SequenceMatcher(a=before, b=after).ratio()
    similarity_diff = []
    similarity_diff.append(click.style(f"--- {change.b_path}", fg="yellow"))
    similarity_diff.append(click.style(f"+++ {change.a_path}", fg="yellow"))
    similarity_diff.append(f"Renamed file, similarity index {r * 100:.2f}%")
    return similarity_diff


def _default_difffunc(
    before_text: str, after_text: str, fromfile: str = "", tofile: str = ""
) -> tuple[Iterable[str], bool]:
    before_lines = before_text.split("\n")
    after_lines = after_text.split("\n")
    diff_lines = difflib.unified_diff(
        before_lines, after_lines, lineterm="", fromfile=fromfile, tofile=tofile
    )
    # never suppress diffs in default difffunc
    return diff_lines, False


def _process_diff(change_type: str, change, diff_func: DiffFunc) -> Iterable[str]:
    difftext = []
    # Because we're diffing the staged changes, the diff objects
    # are backwards, and "added" files are actually being deleted
    # and vice versa for "deleted" files.
    if change_type == "A":
        difftext.append(click.style(f"Deleted file {change.b_path}", fg="red"))
    elif change_type == "D":
        difftext.append(click.style(f"Added file {change.b_path}", fg="green"))
    elif change_type == "R":
        difftext.append(
            click.style(f"Renamed file {change.b_path} => {change.a_path}", fg="yellow")
        )
    else:
        # Other changes should produce a usable diff
        # The diff objects are backwards, so use b_blob as before
        # and a_blob as after.
        before = change.b_blob.data_stream.read().decode("utf-8")
        after = change.a_blob.data_stream.read().decode("utf-8")
        diff_lines, suppress_diff = diff_func(
            before, after, fromfile=change.b_path, tofile=change.a_path
        )
        if not suppress_diff:
            if change.renamed_file:
                # Just compute similarity ratio for renamed files
                # similar to git's diffing
                difftext.append("\n".join(_compute_similarity(change)).strip())
            else:
                diff_lines = [_colorize_diff(line) for line in diff_lines]
                difftext.append("\n".join(diff_lines).strip())

    return difftext


class GitRepo:
    _repo: Repo

    @classmethod
    def clone(cls, repository_url: str, directory: Path, cfg):
        """Clone repository.

        Create initial commit on master branch, if remote is empty."""
        name = None
        email = None
        if cfg:
            name = cfg.username
            email = cfg.usermail
        r = GitRepo(
            repository_url,
            directory,
            force_init=True,
            author_name=name,
            author_email=email,
        )
        try:
            r.checkout()
        except RefError as e:
            click.echo(f" > {e}, creating initial commit for {directory}")
            r.commit("Initial commit")
        except Exception as e:
            raise click.ClickException(
                f"While cloning git repository from {repository_url}: {e}"
            ) from e
        return r

    # pylint: disable=too-many-arguments
    def __init__(
        self,
        remote: Optional[str],
        targetdir: Path,
        force_init=False,
        author_name: Optional[str] = None,
        author_email: Optional[str] = None,
        config=None,
        bare=False,
    ):
        if not force_init and targetdir.exists():
            self._repo = Repo(targetdir)
        else:
            self._repo = Repo.init(targetdir, bare=bare)

        if remote:
            self.remote = remote

        if author_name and author_email:
            self._author = Actor(author_name, author_email)
        else:
            self._author = Actor.committer(self._repo.config_reader())

        if config:
            self._debug = config.debug
            self._trace = config.trace
        else:
            self._debug = False
            self._trace = False

    @property
    def repo(self) -> Repo:
        return self._repo

    @property
    def remote(self) -> str:
        return self._repo.remote().url

    @remote.setter
    def remote(self, remote: str):
        remote = normalize_git_url(remote)
        try:
            self._repo.remote().set_url(remote)
        except ValueError:
            self._repo.create_remote("origin", remote)

        # Generate a best effort push-over-SSH URL for http(s) repo URLs.
        if remote.startswith(("http://", "https://")):
            remote_parts = deconstruct_url(remote)
            # Ignore everything but the host and path parts of the URL to
            # build the push URL
            pushurl = f"ssh://git@{remote_parts.host}{remote_parts.path}"
            self._repo.remote().set_url(pushurl, push=True)

    @property
    def working_tree_dir(self) -> Optional[Path]:
        d = self._repo.working_tree_dir
        if d:
            return Path(d)
        return None

    @property
    def head_short_sha(self) -> str:
        sha = self._repo.head.commit.hexsha
        return self._repo.git.rev_parse(sha, short=6)

    @property
    def _author_env(self) -> dict[str, str]:
        return {
            Actor.env_author_name: self._author.name or "",
            Actor.env_author_email: self._author.email or "",
            Actor.env_committer_name: self._author.name or "",
            Actor.env_committer_email: self._author.email or "",
        }

    @property
    def _null_tree(self) -> Tree:
        """Generate empty Tree for the repo.
        An empty Git tree is represented by the C string "tree 0".
        The hash of the empty tree is always SHA1("tree 0\\0").  This method computes
        the hexdigest of this sha1 and creates a tree object for the empty tree of
        `self._repo`.
        """
        null_tree_sha = hashlib.sha1(b"tree 0\0").hexdigest()  # nosec
        return self._repo.tree(null_tree_sha)

    def _remote_prefix(self) -> str:
        """
        Find prefix of Git remote, will usually be 'origin/'.
        """
        return self._repo.remote().name + "/"

    def _default_version(self) -> str:
        """
        Find default branch of the remote
        """
        try:
            version = self._repo.remote().refs["HEAD"].reference.name
        except IndexError:
            try:
                self._repo.git.remote("set-head", "origin", "--auto")
                version = self._repo.remote().refs["HEAD"].reference.name
            except GitCommandError:
                # If we don't have a remote HEAD, we fall back to creating a master
                # branch.
                version = f"{self._remote_prefix()}master"
        return version.replace(self._remote_prefix(), "", 1)

    def _find_commit_for_version(
        self, version: str, remote_heads: Iterable[FetchInfo]
    ) -> CommitInfo:
        remote_prefix = self._remote_prefix()
        for head in remote_heads:
            tag = None
            branch = None
            headname = head.name
            if headname.startswith(remote_prefix):
                branch = headname.replace(remote_prefix, "", 1)
                headname = branch
            else:
                tag = headname

            if headname == version:
                commit = head.commit
                break
        else:
            # If we haven't found a branch or tag matching the requested version,
            # assume the version is a commit sha.
            commit = self._repo.rev_parse(version)
            branch = None
            tag = None

        return CommitInfo(commit=commit, branch=branch, tag=tag)

    def fetch(
        self, remote: str = "origin", tags: bool = True, prune: bool = True
    ) -> Iterable[FetchInfo]:
        return self._repo.remote(remote).fetch(tags=tags, prune=prune)

    def has_local_branches(self) -> bool:
        local_heads = set(h.name for h in self.repo.heads)
        remote_prefix = self._remote_prefix()
        remote_heads = set(h.name.replace(remote_prefix, "", 1) for h in self.fetch())
        return len(local_heads - remote_heads) > 0

    def has_local_changes(self) -> bool:
        return self._repo.is_dirty() or len(self._repo.untracked_files) > 0

    def _create_worktree(self, worktree: Path, version: str):
        """Create worktree.

        This method expects `worktree` to not exist."""

        # We need to use `git.execute()` for the worktree commands as GitPython only has
        # basic support for worktrees.
        self._repo.git.execute(["git", "worktree", "prune"])
        cmd = ["git", "worktree", "add", "-f", str(worktree), version]
        try:
            self._repo.git.execute(cmd)
        except GitCommandError as e:
            # Assume that GitCommandError is only caused by invalid versions
            raise RefError(f"Failed to checkout revision '{version}'") from e

    def _migrate_to_worktree(self, wtr: GitRepo, worktree: Path, version: str):
        """Migrate non-worktree checkout to worktree."""
        if wtr.has_local_branches() or wtr.has_local_changes():
            raise click.ClickException(
                f"Migrating dependency {worktree} to worktree-based checkout "
                + "would delete uncommitted changes, untracked files, or "
                + "unpushed branches, aborting..."
            )
        click.secho(f" > Removing non-worktree based checkout {worktree}", fg="yellow")
        shutil.rmtree(worktree)
        self._create_worktree(worktree, version)

    def _update_worktree_remote(self, wtr: GitRepo, worktree: Path, version: str):
        """Update existing worktree checkout to new remote.

        Updating the remote for a worktree needs special handling, since we generally
        don't want to update the remote URL for the previously used remote URL's bare
        clone, but instead recreate the worktree from the new remote's bare clone."""
        if wtr.has_local_changes():
            raise click.ClickException(
                f"Switching remote for worktree '{worktree}' would delete "
                + "uncommitted changes or untracked files, aborting..."
            )
        # Remove stale worktree if there are no uncommitted changes
        wtr_common_dir = Path(wtr.repo.common_dir).resolve()
        click.secho(
            f" > Removing stale, but clean worktree {worktree}, "
            + f"bare repo is available at {wtr_common_dir}",
            fg="green",
        )
        wtr.repo.git.execute(["git", "worktree", "remove", str(worktree)])
        self._create_worktree(worktree, version)

    def _checkout_existing_worktree(self, worktree: Path, version: str):
        """Perform checkout if requested worktree directory already exists.

        The heavy work is generally done by `_migrate_to_worktree()`,
        `_update_worktree_remote()` or `checkout()`.
        """
        wtr = GitRepo(None, worktree)
        if not wtr.repo.has_separate_working_tree():
            # If the worktree's common dir is stored in the repository working tree
            # root, we're migrating from a non-worktree checkout to a worktree checkout.
            self._migrate_to_worktree(wtr, worktree, version)
        elif wtr.remote != self.remote:
            # If the existing directory is already a worktree, but we're using a
            # different remote for the requested worktree, we need to recreate the
            # worktree from the new remote's bare clone.
            self._update_worktree_remote(wtr, worktree, version)
        else:
            # Otherwise, we just need to update the worktree's version. We simply use
            # `checkout()` in the worktree to do so.
            wtr.checkout(version)

    def checkout_worktree(self, worktree: Path, version: Optional[str]):
        """Create worktree if it doesn't exist and check out `version` in it.

        If `version` is not provided, the remote's default branch is checked out.

        If a repo which isn't a worktree of `self` is found in the requested worktree
        location, the method will try to replace the old checkout with the requested
        worktree unless there's any local changes (untracked files, uncommitted changes,
        or branches which don't exist upstream).
        """
        # Try to fetch remote heads, so we can actually check them out
        try:
            _ = self.fetch()
        except ValueError:
            pass

        if version is None:
            version = self._default_version()

        # If the worktree directory exists, use `_checkout_existing_worktree()`
        if worktree.is_dir():
            self._checkout_existing_worktree(worktree, version)
            return

        # If the worktree directory doesn't exist yet, create the worktree
        self._create_worktree(worktree, version)

    def initialize_worktree(
        self, worktree: Path, initial_branch: Optional[str] = None
    ) -> None:
        if not initial_branch:
            initial_branch = self._default_version()

        # We need an initial commit to be able to create a worktree. Create initial
        # commit from empty tree.
        initsha = self._repo.git.execute(  # type: ignore[call-overload]
            command=[
                "git",
                "commit-tree",
                "-m",
                "Initial commit",
                self._null_tree.hexsha,
            ],
            env=self._author_env,
        )

        # Create worktree using the provided branch name
        self._repo.git.execute(
            ["git", "worktree", "add", str(worktree), initsha, "-b", initial_branch]
        )

    @property
    def worktrees(self) -> list[GitRepo]:
        """List all worktrees for the repo"""
        # First prune worktrees, to ensure repo worktree state is clean
        self._repo.git.execute(["git", "worktree", "prune"])
        worktrees: list[GitRepo] = []
        wt_list = self._repo.git.execute(
            ["git", "worktree", "list", "--porcelain"],
            as_process=False,
            with_extended_output=False,
            stdout_as_string=True,
        ).splitlines()
        for line in wt_list:
            if " " not in line:
                continue
            k, v = line.split(" ")
            if k == "worktree":
                worktrees.append(GitRepo(None, Path(v)))

        return worktrees

    def checkout(self, version: Optional[str] = None):
        remote_heads = self.fetch()
        if not remote_heads:
            # GitPython's fetch-info parsing chokes on lines like
            # "   (refs/remotes/origin/HEAD has become dangling)"
            # see also https://github.com/gitpython-developers/GitPython/issues/962.
            # We handle this case by simply performing a second fetch which should
            # return fetch-infos with flags = 4 (HEAD_UPTODATE).
            remote_heads = self.fetch()

        if version is None:
            # Handle case where we want the default branch of the remote
            version = self._default_version()

        try:
            commit, branch, tag = self._find_commit_for_version(version, remote_heads)
            if branch:
                # If we found a remote branch for the requested version, find
                # or create a local branch and point HEAD to the branch.
                _head = [h for h in self._repo.heads if h.name == branch]
                if len(_head) > 0:
                    head = _head[0]
                    head.commit = commit
                else:
                    head = self._repo.create_head(branch, commit=commit)

                head.set_tracking_branch(self.repo.remote().refs[branch])
                self._repo.head.set_reference(head)
            elif tag:
                # Simply create detached head pointing to tag
                self._repo.head.set_reference(tag)
            else:
                # Create detached head by setting repo.head.reference as
                # direct ref to commit object.
                self._repo.head.set_reference(commit)

            # Reset working tree to current HEAD reference
            self._repo.head.reset(index=True, working_tree=True)
        except GitCommandError as e:
            raise RefError(f"Failed to checkout revision '{version}'") from e
        except BadName as e:
            raise RefError(f"Revision '{version}' not found in repository") from e

    def stage_all(self, diff_func: DiffFunc = _default_difffunc) -> tuple[str, bool]:
        """Stage all changes.
        This method currently doesn't handle hidden files correctly.

        This method returns a tuple containing the colorized diff of the staged changes
        and a boolean indicating whether any changes were staged.
        """
        index = self._repo.index

        # Stage deletions
        dels = index.diff(None)
        if dels:
            to_remove = []
            for c in dels.iter_change_type("D"):
                to_remove.append(c.b_path)
            if len(to_remove) > 0:
                index.remove(items=to_remove)

        # Stage all remaining changes
        index.add("*")
        # Compute diff of all changes
        try:
            diff = index.diff(self._repo.head.commit)
        except ValueError:
            # Assume that we're in an empty repo if we get a ValueError from
            # index.diff(repo.head.commit). Diff against empty tree.
            diff = index.diff(self._null_tree)

        changed = False
        difftext: list[str] = []
        if diff:
            changed = True
            for ct in diff.change_type:
                # We need to disable type checking here since gitpython expects a value
                # of type `Lit_change_type` in iter_change_type() but returns plain
                # strings in `diff.change_type`.
                for c in diff.iter_change_type(ct):  # type: ignore[arg-type]
                    difftext.extend(_process_diff(ct, c, diff_func))

        return "\n".join(difftext), changed

    def stage_files(self, files: Sequence[str]):
        """Add provided list of files to index."""
        self._repo.index.add(files)

    def commit(self, commit_message: str, amend=False):
        author = self._author

        if self._trace:
            click.echo(f' > Using "{author.name} <{author.email}>" as commit author')

        if amend:
            # We need to call out to `git commit` for amending
            self._repo.git.execute(  # type: ignore[call-overload]
                [
                    "git",
                    "commit",
                    "--amend",
                    "--no-edit",
                    "--reset-author",
                    "-m",
                    commit_message,
                ],
                env=self._author_env,
            )
        else:
            self._repo.index.commit(commit_message, author=author, committer=author)

    def push(
        self, remote: Optional[str] = None, version: Optional[str] = None
    ) -> Iterable[PushInfo]:
        if not remote:
            remote = "origin"
        if not version:
            version = self._default_version()
        return self._repo.remote(remote).push(version)

    def reset(self, working_tree: bool = False):
        self._repo.head.reset(working_tree=working_tree)
