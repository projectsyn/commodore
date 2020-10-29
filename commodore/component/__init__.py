from pathlib import Path as P
from typing import Iterable

from git import Repo


class Component:
    _name: str
    _repo: Repo
    _version: str = "master"
    _dir: P

    # pylint: disable=too-many-arguments
    def __init__(
        self,
        name: str,
        repo_url: str = None,
        version: str = None,
        force_init: bool = False,
        directory: P = None,
    ):
        self._name = name
        if directory:
            self._dir = directory
        else:
            self._dir = component_dir(self.name)
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

    @property
    def version(self) -> str:
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
        # The command `component compile` changes directory so we need an absolute path here.
        # TODO Use self.target_directory when implement https://github.com/projectsyn/commodore/issues/214.
        return P(self.repo.working_tree_dir, "postprocess", "filters.yml")

    def checkout(self):
        self._repo.remote().fetch()
        self._repo.git.checkout(self.version)
        if not self._repo.head.is_detached:
            self._repo.git.pull()


def component_dir(name: str) -> P:
    return P("dependencies") / name
