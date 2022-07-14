from __future__ import annotations

import shutil
import tempfile

from pathlib import Path
from typing import Any, Sequence

import click
from cruft._commands import create as cruft_create

from commodore.dependency_mgmt.discovery import (
    RESERVED_PACKAGE_PATTERN,
    TENANT_PREFIX_PATTERN,
)
from commodore.dependency_templater import Templater, Renderer
from commodore.package import package_dependency_dir


class PackageTemplater(Templater):
    template_url: str
    template_version: str
    test_cases: list[str] = ["defaults"]

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
            "copyright_year": self.today.strftime("%Y"),
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
