from __future__ import annotations

from pathlib import Path

import click

from commodore.config import Config
from commodore.cruft._commands import update as cruft_update
from commodore.dependency_mgmt.discovery import (
    RESERVED_PACKAGE_PATTERN,
    TENANT_PREFIX_PATTERN,
)
from commodore.dependency_templater import Templater
from commodore.package import package_dependency_dir


# pylint: disable=too-many-instance-attributes
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
        return {
            "add_golden": "y" if self.golden_tests else "n",
            "copyright_holder": self.copyright_holder,
            "copyright_year": (
                self.today.strftime("%Y")
                if not self.copyright_year
                else self.copyright_year
            ),
            "github_owner": self.github_owner,
            "name": self.name,
            "slug": self.slug,
            # The template expects the test cases in a single string separated by
            # spaces.
            "test_cases": " ".join(self.test_cases),
        }

    @property
    def deptype(self) -> str:
        return "package"

    def dependency_dir(self) -> Path:
        return package_dependency_dir(self.config.work_dir, self.slug)

    def update(self, print_completion_message: bool = True) -> bool:
        cruft_update(
            self.target_dir,
            cookiecutter_input=False,
            checkout=self.template_version,
            extra_context=self.cookiecutter_args,
        )

        commit_msg = (
            f"Update from template\n\nTemplate version: {self.template_version}"
        )
        if self.template_commit:
            commit_msg += f" ({self.template_commit[:7]})"

        updated = self.commit(commit_msg, init=False)

        if print_completion_message:
            if updated:
                click.secho(
                    f"{self.deptype.capitalize()} {self.name} successfully updated 🎉",
                    bold=True,
                )
            else:
                click.secho(
                    f"{self.deptype.capitalize()} {self.name} already up-to-date 🎉",
                    bold=True,
                )

        return updated
