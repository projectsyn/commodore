import difflib
import hashlib

from collections import namedtuple
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

# We need to import Protocol from typing_extensions for Python 3.7
from typing_extensions import Protocol

import click

from git import Actor, BadName, GitCommandError, Repo

from url_normalize.tools import deconstruct_url, reconstruct_url


class RefError(ValueError):
    pass


CommitInfo = namedtuple("CommitInfo", ["commit", "branch", "tag"])


class DiffFunc(Protocol):
    def __call__(
        self, before_text: str, after_text: str, fromfile: str = "", tofile: str = ""
    ) -> Tuple[Iterable[str], bool]:
        ...


def _normalize_git_ssh(url):
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
    # Import heavy lifting from url_normalize, simplify for Git-SSH usecase
    url = provide_url_scheme(url, "ssh")
    urlparts = deconstruct_url(url)
    urlparts = urlparts._replace(
        userinfo=normalize_userinfo(urlparts.userinfo),
        host=normalize_host(urlparts.host),
        path=normalize_path(urlparts.path, scheme="https"),
    )
    return reconstruct_url(urlparts)


def _colorize_diff(line):
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
) -> Tuple[Iterable[str], bool]:
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
    def create(cls, path: Path):
        return GitRepo(None, path, force_init=True)

    @classmethod
    def clone(cls, repository_url: str, directory: Path, cfg):
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
    ):
        if not force_init and targetdir.exists():
            self._repo = Repo(targetdir)
        else:
            self._repo = Repo.init(targetdir)

        if remote:
            sanitized_remote: str = remote
            if "@" in sanitized_remote and "://" not in sanitized_remote:
                sanitized_remote = _normalize_git_ssh(sanitized_remote)
            self.remote = sanitized_remote

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
    def working_tree_dir(self):
        return self._repo.working_tree_dir

    @property
    def head_short_sha(self):
        sha = self._repo.head.commit.hexsha
        return self._repo.git.rev_parse(sha, short=6)

    @property
    def _null_tree(self):
        """
        An empty Git tree is represented by the C string "tree 0". The hash of the
        empty tree is always SHA1("tree 0\\0").  This method computes the
        hexdigest of this sha1 and creates a tree object for the empty tree of the
        passed repo.
        """
        null_tree_sha = hashlib.sha1(b"tree 0\0").hexdigest()  # nosec
        return self._repo.tree(null_tree_sha)

    def _remote_prefix(self):
        """
        Find prefix of Git remote, will usually be 'origin/'.
        """
        return self._repo.remote().name + "/"

    def _default_version(self):
        """
        Find default branch of the remote
        """
        try:
            version = self._repo.remote().refs["HEAD"].reference.name
        except IndexError:
            self._repo.git.remote("set-head", "origin", "--auto")
            version = self._repo.remote().refs["HEAD"].reference.name
        return version.replace(self._remote_prefix(), "", 1)

    def _find_commit_for_version(self, version, remote_heads):
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
            commit = version
            branch = None
            tag = None

        return CommitInfo(commit=commit, branch=branch, tag=tag)

    def checkout(self, version: Optional[str] = None):
        remote_heads = self._repo.remote().fetch(prune=True, tags=True)
        if version is None:
            # Handle case where we want the default branch of the remote
            version = self._default_version()

        commit, branch, tag = self._find_commit_for_version(version, remote_heads)

        try:
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
                rev = self._repo.rev_parse(commit)
                self._repo.head.set_reference(rev)

            # Reset working tree to current HEAD reference
            self._repo.head.reset(index=True, working_tree=True)
        except GitCommandError as e:
            raise RefError(f"Failed to checkout revision '{version}'") from e
        except BadName as e:
            raise RefError(f"Revision '{version}' not found in repository") from e

    def stage_all(self, diff_func: DiffFunc = _default_difffunc):
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
        difftext: List[str] = []
        if diff:
            changed = True
            for ct in diff.change_type:
                # We need to disable type checking here since gitpython expects a value
                # of type `Lit_change_type` in iter_change_type() but returns plain
                # strings in `diff.change_type`.
                for c in diff.iter_change_type(ct):  # type: ignore[arg-type]
                    difftext.extend(_process_diff(ct, c, diff_func))

        return "\n".join(difftext), changed

    def commit(self, commit_message):
        author = self._author

        if self._trace:
            click.echo(f' > Using "{author.name} <{author.email}>" as commit author')

        self._repo.index.commit(commit_message, author=author, committer=author)

    def push(self, remote: Optional[str] = None):
        if not remote:
            remote = "origin"
        return self._repo.remote(remote).push()

    def reset(self, working_tree: bool = False):
        self._repo.head.reset(working_tree=working_tree)
