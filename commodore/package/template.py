from __future__ import annotations

import json
import shutil
import tempfile

from pathlib import Path
from typing import Any, Optional, Sequence

import click


from commodore.config import Config
from commodore.cruft._commands import create as cruft_create, update as cruft_update
from commodore.dependency_mgmt.discovery import (
    RESERVED_PACKAGE_PATTERN,
    TENANT_PREFIX_PATTERN,
)
from commodore.dependency_templater import Templater, Renderer
from commodore.package import package_dependency_dir


# pylint: disable=too-many-instance-attributes
class PackageTemplater(Templater):
    template_url: str
    template_version: str
    template_commit: str
    test_cases: list[str] = ["defaults"]
    copyright_year: Optional[str] = None

    @classmethod
    def from_existing(cls, config: Config, package_path: Path):
        if not package_path.is_dir():
            raise click.ClickException("Provided package path isn't a directory")
        with open(package_path / ".cruft.json", encoding="utf-8") as cfg:
            cruft_json = json.load(cfg)

        cookiecutter_args = cruft_json["context"]["cookiecutter"]
        t = PackageTemplater(
            config, cookiecutter_args["slug"], name=cookiecutter_args["name"]
        )
        t.output_dir = package_path.absolute().parent
        t.template_url = cruft_json["template"]
        if cruft_json["checkout"]:
            t.template_version = cruft_json["checkout"]
        if cruft_json["commit"]:
            t.template_commit = cruft_json["commit"]

        if "test_cases" in cookiecutter_args:
            t.test_cases = cookiecutter_args["test_cases"].split(" ")
        t.golden_tests = cookiecutter_args["add_golden"] == "y"
        t.github_owner = cookiecutter_args["github_owner"]
        t.copyright_holder = cookiecutter_args["copyright_holder"]
        t.copyright_year = cookiecutter_args["copyright_year"]
        return t

    def _cruft_renderer(
        self,
        template_location: str,
        extra_context: dict[str, Any],
        no_input: bool,
        output_dir: Path,
    ):
        """Render package cookiecutter template in tempdir and move the results to
        `output_dir/pkg.<slug>`, because as far as I can see we can't configure
        cruft/cookiecutter to create a directory named `pkg.<slug>` except if we
        change the slug itself, which would need a bunch of template changes.
        """

        # Because we render the template in a temp directory and move it to the desired
        # target directory, we don't need argument `output_dir` which is set to
        # `self.target_dir.parent` when the renderer function is called by the base
        # class, and instead move the final rendered package to `self.target_dir`
        # ourselves.
        _ = output_dir
        tmpdir = Path(tempfile.mkdtemp())
        cruft_create(
            template_location,
            checkout=self.template_version,
            extra_context=extra_context,
            no_input=no_input,
            output_dir=tmpdir,
        )
        shutil.move(str(tmpdir / self.slug), self.target_dir)
        shutil.rmtree(tmpdir)

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

    @property
    def template_renderer(self) -> Renderer:
        return self._cruft_renderer

    @property
    def target_dir(self) -> Path:
        if self.output_dir:
            return self.output_dir / self.slug

        return package_dependency_dir(self.config.work_dir, self.slug)

    @property
    def template(self) -> str:
        return self.template_url

    @property
    def additional_files(self) -> Sequence[str]:
        return [
            ".github",
            ".gitignore",
            ".*.yml",
            ".editorconfig",
            ".cruft.json",
        ]

    def update(self):
        cruft_update(
            self.target_dir,
            cookiecutter_input=False,
            checkout=self.template_version,
            extra_context=self.cookiecutter_args,
        )

        self.commit(
            "Update from template\n\n"
            + f"Template version: {self.template_version} ({self.template_commit[:7]})"
        )

        click.secho(
            f"{self.deptype.capitalize()} {self.name} successfully updated 🎉", bold=True
        )
