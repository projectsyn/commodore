from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path as P
from typing import Optional

import _gojsonnet
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
    _aliases: dict[str, tuple[str, str]]
    _work_dir: Optional[P]

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
        self._aliases = {self.name: (self.version or "", self.sub_path or "")}
        self._work_dir = work_dir

    @property
    def name(self) -> str:
        return self._name

    @property
    def repo(self) -> GitRepo:
        if not self._repo:
            if self._dependency:
                dep_repo = self._dependency.bare_repo
                author_name = (
                    dep_repo.author.name if hasattr(dep_repo, "author") else None
                )
                author_email = (
                    dep_repo.author.email if hasattr(dep_repo, "author") else None
                )
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
    def sub_path(self) -> str:
        return self._sub_path

    @property
    def repo_directory(self) -> P:
        return self._dir

    @property
    def work_directory(self) -> Optional[P]:
        return self._work_dir

    @property
    def target_directory(self) -> P:
        return self.alias_directory(self.name)

    @property
    def target_dir(self) -> P:
        return self.target_directory

    @property
    def class_file(self) -> P:
        return self.alias_class_file(self.name)

    @property
    def defaults_file(self) -> P:
        return self.alias_defaults_file(self.name)

    def alias_directory(self, alias: str) -> P:
        if not self._dependency:
            return self._dir / self._sub_path
        apath = self._dependency.get_component(alias)
        if not apath:
            raise ValueError(f"unknown alias {alias} for component {self.name}")
        if alias not in self._aliases:
            raise ValueError(
                f"alias {alias} for component {self.name} has not been registered"
            )
        return apath / self._aliases[alias][1]

    def alias_class_file(self, alias: str) -> P:
        return self.alias_directory(alias) / "class" / f"{self.name}.yml"

    def alias_defaults_file(self, alias: str) -> P:
        return self.alias_directory(alias) / "class" / "defaults.yml"

    def has_alias(self, alias: str):
        return alias in self._aliases

    @property
    def lib_files(self) -> Iterable[P]:
        # NOTE(sg): Usage of yield makes the whole function return a generator.
        # So if the top-level condition is false, this should immediately raise
        # a StopIteration exception. Mypy has started to complain about the
        # `return []` that was previously part of this function.
        lib_dir = self.target_directory / "lib"
        if lib_dir.exists():
            for e in lib_dir.iterdir():
                # Skip hidden files in lib directory
                if not e.name.startswith("."):
                    yield e

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

    def register_alias(self, alias: str, version: str, sub_path: str = ""):
        if not self._work_dir:
            raise ValueError(
                f"Can't register alias on component {self.name} "
                + "which isn't configured with a working directory"
            )
        if alias in self._aliases:
            raise ValueError(
                f"alias {alias} already registered on component {self.name}"
            )
        self._aliases[alias] = (version, sub_path)
        if self._dependency:
            self._dependency.register_component(
                alias, component_dir(self._work_dir, alias)
            )

    def checkout_alias(
        self, alias: str, alias_dependency: Optional[MultiDependency] = None
    ):
        if alias not in self._aliases:
            raise ValueError(
                f"alias {alias} is not registered on component {self.name}"
            )

        if alias_dependency:
            alias_dependency.checkout_component(alias, self._aliases[alias][0])
        elif self._dependency:
            self._dependency.checkout_component(alias, self._aliases[alias][0])

    def is_checked_out(self) -> bool:
        return self.target_dir is not None and self.target_dir.is_dir()

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
            output = _gojsonnet.evaluate_file(
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
