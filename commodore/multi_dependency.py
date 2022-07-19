from __future__ import annotations

from pathlib import Path
from typing import Optional

from url_normalize.tools import deconstruct_url

from commodore.gitrepo import GitRepo, normalize_git_url


class MultiDependency:
    _repo: GitRepo
    _components: dict[str, Path]
    _packages: dict[str, Path]

    def __init__(self, repo_url: str, dependencies_dir: Path):
        repo_dir = dependency_dir(dependencies_dir, repo_url)
        self._repo = GitRepo(repo_url, repo_dir, bare=True)
        self._components = {}
        self._packages = {}

    @property
    def url(self) -> str:
        return self._repo.remote

    @url.setter
    def url(self, repo_url: str):
        self._repo.remote = repo_url

    @property
    def repo_directory(self) -> Path:
        return Path(self._repo.repo.common_dir).resolve().absolute()

    def get_component(self, name: str) -> Optional[Path]:
        return self._components.get(name)

    def register_component(self, name: str, target_dir: Path):
        if name in self._components:
            raise ValueError(f"component {name} already registered")

        self._components[name] = target_dir

    def deregister_component(self, name: str):
        try:
            del self._components[name]
        except KeyError as e:
            raise ValueError(f"can't deregister unknown component {name}") from e

    def checkout_component(self, name: str, version: str):
        """Create or update worktree for component `name`."""
        target_dir = self.get_component(name)
        if not target_dir:
            raise ValueError(f"can't checkout unknown component {name}")
        self._repo.checkout_worktree(target_dir, version=version)

    def get_package(self, name: str) -> Optional[Path]:
        return self._packages.get(name)

    def register_package(self, name: str, target_dir: Path):
        if name in self._packages:
            raise ValueError(f"package {name} already registered")

        self._packages[name] = target_dir

    def deregister_package(self, name: str):
        try:
            del self._packages[name]
        except KeyError as e:
            raise ValueError(f"can't deregister unknown package {name}") from e

    def checkout_package(self, name: str, version: str):
        """Create or update worktree for package `name`."""
        target_dir = self.get_package(name)
        if not target_dir:
            raise ValueError(f"can't checkout unknown package {name}")
        self._repo.checkout_worktree(target_dir, version=version)

    def initialize_worktree(self, target_dir: Path) -> None:
        """Initialize a worktree in `target_dir`."""
        self._repo.initialize_worktree(target_dir)

    def has_checkouts(self) -> bool:
        return len(self._repo.worktrees) > 1


def dependency_dir(base_dir: Path, repo_url: str) -> Path:
    return base_dir / ".repos" / dependency_key(repo_url)


def dependency_key(repo_url: str) -> str:
    """Create normalized and scheme-agnostic key for the given repo URL.

    This is also used to determine the subpath where the bare checkout is created."""
    repo_url = normalize_git_url(repo_url)
    url_parts = deconstruct_url(repo_url)
    depkey = ""
    if url_parts.host:
        depkey = f"{url_parts.host}/"
    return depkey + url_parts.path[1:]
