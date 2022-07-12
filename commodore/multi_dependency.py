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

    def get_component(self, name: str) -> Optional[Path]:
        return self._components.get(name)

    def register_component(self, name: str, target_dir: Path):
        if name in self._components:
            raise ValueError(f"component {name} already registered")

        self._components[name] = target_dir

    def deregister_component(self, name: str) -> bool:
        try:
            del self._components[name]
            return True
        except KeyError:
            return False

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

    def deregister_package(self, name: str) -> bool:
        try:
            del self._packages[name]
            return True
        except KeyError:
            return False

    def checkout_package(self, name: str, version: str):
        """Create or update worktree for package `name`."""
        target_dir = self.get_package(name)
        if not target_dir:
            raise ValueError(f"can't checkout unknown package {name}")
        self._repo.checkout_worktree(target_dir, version=version)


def dependency_dir(base_dir: Path, repo_url: str) -> Path:
    # Normalize URL here, as we don't require that we always are passed a normalized
    # URL.
    repo_url = normalize_git_url(repo_url)
    url_parts = deconstruct_url(repo_url)
    return base_dir / ".repos" / url_parts.host / url_parts.path[1:]
