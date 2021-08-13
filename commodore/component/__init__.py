from collections import namedtuple
from pathlib import Path as P
from typing import Iterable, Optional

import _jsonnet
import click

from git import Repo, BadName, GitCommandError
from url_normalize.tools import deconstruct_url

from commodore.git import RefError


CommitInfo = namedtuple("CommitInfo", ["commit", "branch", "tag"])


class Component:
    _name: str
    _repo: Repo
    _version: Optional[str] = None
    _dir: P

    # pylint: disable=too-many-arguments
    def __init__(
        self,
        name: str,
        work_dir: P = None,
        repo_url: str = None,
        version: str = None,
        force_init: bool = False,
        directory: P = None,
    ):
        self._name = name
        if directory:
            self._dir = directory
        elif work_dir:
            self._dir = component_dir(work_dir, self.name)
        else:
            raise click.ClickException(
                "Either `work_dir` or `directory` must be provided."
            )
        self._init_repo(force_init)
        if repo_url:
            self.repo_url = repo_url
        if version:
            self.version = version

    def _init_repo(self, force: bool):
        path = self.target_directory
        if not force and path.exists():
            self._repo = Repo(path)
        else:
            self._repo = Repo.init(path)

    @property
    def name(self) -> str:
        return self._name

    @property
    def repo(self) -> Repo:
        return self._repo

    @property
    def repo_url(self) -> str:
        return self._repo.remote().url

    @repo_url.setter
    def repo_url(self, url: str):
        try:
            self._repo.remote().set_url(url)
        except ValueError:
            self._repo.create_remote("origin", url)

        # Generate a best effort push-over-SSH URL for http(s) repo URLs.
        if url.startswith(("http://", "https://")):
            url_parts = deconstruct_url(url)
            # Ignore everything but the host and path parts of the URL to
            # build the push URL
            pushurl = f"ssh://git@{url_parts.host}{url_parts.path}"
            self._repo.remote().set_url(pushurl, push=True)

    @property
    def version(self) -> Optional[str]:
        return self._version

    @version.setter
    def version(self, version: str):
        self._version = version

    @property
    def target_directory(self) -> P:
        return self._dir

    @property
    def class_file(self) -> P:
        return self.target_directory / "class" / f"{self.name}.yml"

    @property
    def defaults_file(self) -> P:
        return self.target_directory / "class" / "defaults.yml"

    @property
    def lib_files(self) -> Iterable[P]:
        lib_dir = self.target_directory / "lib"
        if lib_dir.exists():
            return lib_dir.iterdir()

        return []

    @property
    def filters_file(self) -> P:
        return self.target_directory / "postprocess" / "filters.yml"

    @property
    def parameters_key(self):
        return component_parameters_key(self.name)

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

    def checkout(self):
        remote_heads = self._repo.remote().fetch(prune=True, tags=True)
        version = self._version
        if self._version is None:
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
                self._repo.head.reference = head
            elif tag:
                # Simply create detached head pointing to tag
                self._repo.head.reference = tag
            else:
                # Create detached head by setting repo.head.reference as
                # direct ref to commit object.
                rev = self._repo.rev_parse(commit)
                self._repo.head.reference = rev

            # Reset working tree to current HEAD reference
            self._repo.head.reset(index=True, working_tree=True)
        except GitCommandError as e:
            raise RefError(f"Failed to checkout revision '{self.version}'") from e
        except BadName as e:
            raise RefError(f"Revision '{self.version}' not found in repository") from e

    def render_jsonnetfile_json(self, component_params):
        """
        Render jsonnetfile.json from jsonnetfile.jsonnet
        """
        jsonnetfile_jsonnet = self._dir / "jsonnetfile.jsonnet"
        jsonnetfile_json = self._dir / "jsonnetfile.json"
        if jsonnetfile_jsonnet.is_file():
            if jsonnetfile_json.name in self.repo.tree():
                click.secho(
                    f" > [WARN] Component {self.name} repo contains both jsonnetfile.json and jsonnetfile.jsonnet, "
                    + "continuing with jsonnetfile.jsonnet",
                    fg="yellow",
                )
            # pylint: disable=c-extension-no-member
            output = _jsonnet.evaluate_file(
                str(jsonnetfile_jsonnet),
                ext_vars=component_params.get("jsonnetfile_parameters", {}),
            )
            with open(self._dir / "jsonnetfile.json", "w", encoding="utf-8") as fp:
                fp.write(output)


def component_dir(work_dir: P, name: str) -> P:
    return work_dir / "dependencies" / name


def component_parameters_key(name: str) -> str:
    return name.replace("-", "_")
