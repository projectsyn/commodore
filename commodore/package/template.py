from __future__ import annotations

from pathlib import Path

import click

from commodore.config import Config
from commodore.dependency_mgmt.discovery import (
    RESERVED_PACKAGE_PATTERN,
    TENANT_PREFIX_PATTERN,
)
from commodore.dependency_templater import Templater
from commodore.package import package_dependency_dir


class PackageTemplater(Templater):
    _test_cases: list[str] = ["defaults"]

    @classmethod
    def from_existing(cls, config: Config, path: Path):
        return cls._base_from_existing(config, path, "package")

    def _initialize_from_cookiecutter_args(self, cookiecutter_args: dict[str, str]):
        super()._initialize_from_cookiecutter_args(cookiecutter_args)
        if "test_cases" in cookiecutter_args:
            self.test_cases = cookiecutter_args["test_cases"].split(" ")

    @property
    def test_cases(self) -> list[str]:
        """Return list of test cases.

        The getter deduplicates the stored list before returning it.

        Don't use `append()` on the returned list to add test cases to the package, as
        the getter returns a copy of the list stored in the object."""
        cases = []
        for t in self._test_cases:
            if t not in cases:
                cases.append(t)
        return cases

    @test_cases.setter
    def test_cases(self, test_cases: list[str]):
        self._test_cases = test_cases

    def _validate_slug(self, value: str):
        # First perform default slug checks
        slug = super()._validate_slug(value)
        # Then perform additional checks for package slug
        if RESERVED_PACKAGE_PATTERN.match(slug):
            raise click.ClickException(f"Package can't use reserved slug '{slug}'")
        if TENANT_PREFIX_PATTERN.match(slug):
            raise click.ClickException(
                "Package slug can't use reserved tenant prefix 't-'"
            )
        return slug

    @property
    def cookiecutter_args(self) -> dict[str, str]:
        args = super().cookiecutter_args
        # The template expects the test cases in a single string separated by spaces.
        args["test_cases"] = " ".join(self.test_cases)
        return args

    @property
    def deptype(self) -> str:
        return "package"

    def dependency_dir(self) -> Path:
        return package_dependency_dir(self.config.work_dir, self.slug)
