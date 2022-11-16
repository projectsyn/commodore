from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path as P
from typing import Optional

import _jsonnet
import click
import git

from commodore.gitrepo import GitRepo
from commodore.multi_dependency import MultiDependency


class Component:
    _name: str
    _repo: Optional[GitRepo]
    _dependency: Optional[MultiDependency] = None
    _version: Optional[str] = None
    _dir: P
    _sub_path: str

    @classmethod
    def clone(cls, cfg, clone_url: str, name: str, version: str = "master"):
        cdep = cfg.register_dependency_repo(clone_url)
        c = Component(
            name,
            cdep,
            directory=component_dir(cfg.work_dir, name),
            version=version,
        )
        c.checkout()
        return c

    # pylint: disable=too-many-arguments
    def __init__(
        self,
        name: str,
        dependency: Optional[MultiDependency],
        work_dir: Optional[P] = None,
        version: Optional[str] = None,
        directory: Optional[P] = None,
        sub_path: str = "",
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
        if dependency:
            self._dependency = dependency
            self._dependency.register_component(self.name, self._dir)
        self.version = version
        self._sub_path = sub_path
        self._repo = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def repo(self) -> GitRepo:
        if not self._repo:
            if self._dependency:
                dep_repo = self._dependency.bare_repo
                author_name = dep_repo.author.name
                author_email = dep_repo.author.email
            else:
                # Fall back to author detection if we don't have a dependency
                author_name = None
                author_email = None
            self._repo = GitRepo(
                None,
                self._dir,
                author_name=author_name,
                author_email=author_email,
            )
        return self._repo

    @property
    def dependency(self) -> MultiDependency:
        if self._dependency is None:
            raise ValueError(
                f"Dependency for component {self._name} hasn't been initialized"
            )
        return self._dependency

    @dependency.setter
    def dependency(self, dependency: Optional[MultiDependency]):
        """Update the GitRepo backing the component"""
        if self._dependency:
            self._dependency.deregister_component(self.name)
        if dependency:
            dependency.register_component(self.name, self._dir)
        self._dependency = dependency
        # Clear worktree GitRepo wrapper when we update the component's backing
        # dependency. The new GitRepo wrapper will be created on the nex access of
        # `repo`.
        self._repo = None

    @property
    def repo_url(self) -> str:
        if self._dependency is None:
            raise ValueError(
                f"Dependency for component {self._name} hasn't been initialized"
            )
        return self._dependency.url

    @property
    def version(self) -> Optional[str]:
        return self._version

    @version.setter
    def version(self, version: str):
        self._version = version

    @property
    def repo_directory(self) -> P:
        return self._dir

    @property
    def target_directory(self) -> P:
        return self._dir / self._sub_path

    @property
    def target_dir(self) -> P:
        return self.target_directory

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
            for e in lib_dir.iterdir():
                # Skip hidden files in lib directory
                if not e.name.startswith("."):
                    yield e

        return []

    def get_library(self, libname: str) -> Optional[P]:
        lib_dir = self.target_directory / "lib"
        if not lib_dir.exists():
            return None

        for f in self.lib_files:
            if f.absolute() == P(lib_dir / libname).absolute():
                return f.absolute()

        return None

    @property
    def parameters_key(self):
        return component_parameters_key(self.name)

    def checkout(self):
        if self._dependency is None:
            raise ValueError(
                f"Dependency for component {self._name} hasn't been initialized"
            )
        self._dependency.checkout_component(self.name, self.version)

    def checkout_is_dirty(self) -> bool:
        if self._dependency:
            dep_repo = self._dependency.bare_repo
            author_name = dep_repo.author.name
            author_email = dep_repo.author.email
            worktree = self._dependency.get_component(self.name)
        else:
            author_name = None
            author_email = None
            worktree = self.target_dir

        if worktree and worktree.is_dir():
            r = GitRepo(
                None, worktree, author_name=author_name, author_email=author_email
            )
            return r.repo.is_dirty()
        else:
            return False

    def render_jsonnetfile_json(self, component_params):
        """
        Render jsonnetfile.json from jsonnetfile.jsonnet
        """
        jsonnetfile_jsonnet = self._dir / "jsonnetfile.jsonnet"
        jsonnetfile_json = self._dir / "jsonnetfile.json"
        if jsonnetfile_jsonnet.is_file():
            try:
                if jsonnetfile_json.name in self.repo.repo.tree():
                    click.secho(
                        f" > [WARN] Component {self.name} repo contains both jsonnetfile.json "
                        + "and jsonnetfile.jsonnet, continuing with jsonnetfile.jsonnet",
                        fg="yellow",
                    )
            except git.InvalidGitRepositoryError:
                pass
            # pylint: disable=c-extension-no-member
            output = _jsonnet.evaluate_file(
                str(jsonnetfile_jsonnet),
                ext_vars=component_params.get("jsonnetfile_parameters", {}),
            )
            with open(self._dir / "jsonnetfile.json", "w", encoding="utf-8") as fp:
                fp.write(output)
                fp.write("\n")


def component_dir(work_dir: P, name: str) -> P:
    return work_dir / "dependencies" / name


def component_parameters_key(name: str) -> str:
    return name.replace("-", "_")
