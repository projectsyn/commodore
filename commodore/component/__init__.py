from pathlib import Path as P
from typing import NamedTuple

from git import Repo


# Python 3.9 changed typing.NamedTuple to be a function that can be inherited
# from. This trips up pylint, cf. https://github.com/PyCQA/pylint/issues/3876.
# pylint: disable=inherit-non-class
# pylint: disable=too-few-public-methods
class Component(NamedTuple):
    name: str
    repo: Repo
    repo_url: str
    version: str = "master"

    @property
    def target_directory(self) -> P:
        return P("dependencies") / self.name
