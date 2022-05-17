from __future__ import annotations

import datetime
import re

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional, Protocol, Sequence

import click

from commodore.config import Config
from commodore.gitrepo import GitRepo

SLUG_REGEX = re.compile("^[a-z][a-z0-9-]+[a-z0-9]$")


class Renderer(Protocol):
    def __call__(
        self,
        template_location: str,
        extra_context: dict[str, Any],
        no_input: bool,
        output_dir: Path,
    ):
        ...


class Templater(ABC):
    config: Config
    _slug: str
    _name: Optional[str]
    github_owner: str
    copyright_holder: str
    golden_tests: bool
    today: datetime.date

    def __init__(self, config: Config, slug: str, name: Optional[str]):
        self.config = config
        self.slug = slug
        self._name = name
        self.today = datetime.date.today()

    def _validate_slug(self, value: str) -> str:
        if value.startswith(f"{self.deptype}-"):
            raise click.ClickException(
                f"The {self.deptype} slug may not start with '{self.deptype}-'"
            )
        if not SLUG_REGEX.match(value):
            raise click.ClickException(
                f"The {self.deptype} slug must match '{SLUG_REGEX.pattern}'"
            )
        return value

    @property
    def slug(self) -> str:
        return self._slug

    @slug.setter
    def slug(self, value: str):
        self._slug = self._validate_slug(value)

    @property
    def name(self) -> str:
        if not self._name:
            return self.slug
        return self._name

    @property
    def repo_url(self) -> str:
        return f"git@github.com:{self.github_owner}/{self.deptype}-{self.slug}.git"

    @property
    @abstractmethod
    def deptype(self) -> str:
        ...

    @property
    @abstractmethod
    def target_dir(self) -> Path:
        ...

    @property
    @abstractmethod
    def template(self) -> str:
        ...

    @property
    @abstractmethod
    def template_renderer(self) -> Renderer:
        ...

    @property
    @abstractmethod
    def cookiecutter_args(self) -> dict[str, str]:
        ...

    @property
    @abstractmethod
    def additional_files(self) -> Sequence[str]:
        ...

    def create(self) -> None:
        click.secho(f"Adding {self.deptype} {self.name}...", bold=True)

        if self.target_dir.exists():
            raise click.ClickException(
                f"Unable to add {self.deptype} {self.name}: "
                + f"{self.target_dir} already exists."
            )

        self.template_renderer(
            self.template,
            no_input=True,
            output_dir=self.target_dir.parent,
            extra_context=self.cookiecutter_args,
        )

        repo = GitRepo(self.repo_url, targetdir=self.target_dir, force_init=True)
        repo.stage_all()
        repo.stage_files(self.additional_files)
        repo.commit("Initial commit")

        click.secho(
            f"{self.deptype.capitalize()} {self.name} successfully added 🎉", bold=True
        )
