from pathlib import Path as P

from git import Repo


class Component:
    _name: str
    _repo: Repo
    _repo_url: str
    _version: str = "master"

    def __init__(
        self, name: str, repo: Repo = None, repo_url: str = None, version: str = None
    ):
        self._name = name
        if repo:
            self._repo = repo
        if repo_url:
            self._repo_url = repo_url
        if version:
            self._version = version

    @property
    def name(self) -> str:
        return self._name

    @property
    def repo(self) -> Repo:
        return self._repo

    @repo.setter
    def repo(self, repo: Repo):
        self._repo = repo

    @property
    def repo_url(self) -> str:
        return self._repo_url

    @repo_url.setter
    def repo_url(self, repo_url: str):
        self._repo_url = repo_url

    @property
    def version(self) -> str:
        return self._version

    @version.setter
    def version(self, version: str):
        self._version = version

    @property
    def target_directory(self) -> P:
        return P("dependencies") / self.name
