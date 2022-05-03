from pathlib import Path
from typing import Optional

from commodore.gitrepo import GitRepo


class Package:
    """
    Class representing a config package.
    Used to abstract from details of cloning/checking out the correct package repo and
    version
    """

    def __init__(
        self,
        name: str,
        target_dir: Path,
        url: Optional[str] = None,
        version: Optional[str] = None,
    ):
        self._name = name
        self._version = version
        self._gitrepo = GitRepo(remote=url, targetdir=target_dir)

    @property
    def url(self) -> Optional[str]:
        return self._gitrepo.remote

    @property
    def version(self) -> Optional[str]:
        return self._version

    @property
    def target_dir(self) -> Optional[Path]:
        return self._gitrepo.working_tree_dir

    def checkout(self):
        self._gitrepo.checkout(self._version)
