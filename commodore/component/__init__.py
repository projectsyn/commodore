from pathlib import Path as P

from git import Repo


class Component:
    _name: str
    _repo: Repo
    _version: str = "master"

    def __init__(
        self,
        name: str,
        repo_url: str = None,
        version: str = None,
        force_init: bool = False,
    ):
        self._name = name
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
        return component_dir(self.name)

    def checkout(self):
        self._repo.remote().fetch()
        self._repo.git.checkout(self.version)
        if not self._repo.head.is_detached:
            self._repo.git.pull()


def component_dir(name: str) -> P:
    return P("dependencies") / name
