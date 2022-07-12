from pathlib import Path
from typing import Optional

from commodore.multi_dependency import MultiDependency


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
    def target_dir(self) -> Optional[Path]:
        worktree = self._dependency.get_package(self._name)
        if not worktree:
            return None

        return worktree / self._sub_path

    def checkout(self):
        self._dependency.checkout_package(self._name, self._version)


def package_dependency_dir(work_dir: Path, pname: str) -> Path:
    return work_dir / "dependencies" / f"pkg.{pname}"
