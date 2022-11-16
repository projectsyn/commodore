from pathlib import Path
from typing import Optional

from commodore.multi_dependency import MultiDependency
from commodore.gitrepo import GitRepo


class Package:
    """
    Class representing a config package.
    Used to abstract from details of cloning/checking out the correct package repo and
    version
    """

    _gitrepo: Optional[GitRepo]

    @classmethod
    def clone(cls, cfg, clone_url: str, name: str, version: str = "master"):
        pdep = cfg.register_dependency_repo(clone_url)
        p = Package(
            name,
            pdep,
            package_dependency_dir(cfg.work_dir, name),
            version=version,
        )
        p.checkout()
        return p

    # pylint: disable=too-many-arguments
    def __init__(
        self,
        name: str,
        dependency: MultiDependency,
        target_dir: Path,
        version: Optional[str] = None,
        sub_path: str = "",
    ):
        self._name = name
        self._version = version
        self._sub_path = sub_path
        self._dependency = dependency
        self._dependency.register_package(name, target_dir)
        self._gitrepo = None

    @property
    def url(self) -> Optional[str]:
        return self._dependency.url

    @property
    def version(self) -> Optional[str]:
        return self._version

    @property
    def sub_path(self) -> str:
        return self._sub_path

    @property
    def repository_dir(self) -> Optional[Path]:
        return self._dependency.get_package(self._name)

    @property
    def repo(self) -> Optional[GitRepo]:
        if not self._gitrepo and self.target_dir and self.target_dir.is_dir():
            if self._dependency:
                dep_repo = self._dependency.bare_repo
                author_name = dep_repo.author.name
                author_email = dep_repo.author.email
            else:
                # Fall back to author detection if we don't have a dependency
                author_name = None
                author_email = None
            self._gitrepo = GitRepo(
                None,
                self.target_dir,
                author_name=author_name,
                author_email=author_email,
            )
        return self._gitrepo

    @property
    def target_dir(self) -> Optional[Path]:
        worktree = self._dependency.get_package(self._name)
        if not worktree:
            return None

        return worktree / self._sub_path

    def checkout(self):
        self._dependency.checkout_package(self._name, self._version)

    def checkout_is_dirty(self) -> bool:
        dep_repo = self._dependency.bare_repo
        author_name = dep_repo.author.name
        author_email = dep_repo.author.email
        worktree = self._dependency.get_package(self._name)

        if worktree and worktree.is_dir():
            r = GitRepo(
                None, worktree, author_name=author_name, author_email=author_email
            )
            return r.repo.is_dirty()
        else:
            return False


def package_dependency_dir(work_dir: Path, pname: str) -> Path:
    return work_dir / "dependencies" / f"pkg.{pname}"
