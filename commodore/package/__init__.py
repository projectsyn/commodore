from pathlib import Path
from typing import Optional

from commodore.gitrepo import GitRepo


class Package:
    """
    Class representing a config package.
    Used to abstract from details of cloning/checking out the correct package repo and
    version
    """

    # pylint: disable=too-many-arguments
    def __init__(
        self,
        name: str,
        target_dir: Path,
        url: Optional[str] = None,
        version: Optional[str] = None,
        sub_path: str = "",
    ):
        self._name = name
        self._version = version
        self._gitrepo = GitRepo(remote=url, targetdir=target_dir)
        self._sub_path = sub_path

    @property
    def url(self) -> Optional[str]:
        return self._gitrepo.remote

    @property
    def version(self) -> Optional[str]:
        return self._version

    @property
    def sub_path(self) -> str:
        return self._sub_path

    @property
    def repository_dir(self) -> Optional[Path]:
        return self._gitrepo.working_tree_dir

    @property
    def target_dir(self) -> Optional[Path]:
        if not self._gitrepo.working_tree_dir:
            return None

        return self._gitrepo.working_tree_dir / self._sub_path

    def checkout(self):
        self._gitrepo.checkout(self._version)


def package_dependency_dir(work_dir: Path, pname: str) -> Path:
    return work_dir / "dependencies" / f"pkg.{pname}"
