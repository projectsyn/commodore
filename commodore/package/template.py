from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from cruft._commands import create as cruft_create

from commodore.dependency_templater import Templater, Renderer

# TODO
# * configurable template URL / revision
# * configurable output dir (maybe also for component template)
# * verify that cruft generates the right config
# * check that we can propagate updates with `cruft update`


class PackageTemplater(Templater):
    template_url: str
    template_version: str

    def _cruft_renderer(
        self,
        template_location: str,
        extra_context: dict[str, Any],
        no_input: bool,
        output_dir: Path,
    ):
        cruft_create(
            template_location,
            checkout=self.template_version,
            extra_context=extra_context,
            no_input=no_input,
            output_dir=output_dir,
        )

    @property
    def cookiecutter_args(self) -> dict[str, str]:
        return {
            "add_golden": "y" if self.golden_tests else "n",
            "copyright_holder": self.copyright_holder,
            "copyright_year": self.today.strftime("%Y"),
            "github_owner": self.github_owner,
            "name": self.name,
            "slug": self.slug,
        }

    @property
    def deptype(self) -> str:
        return "package"

    @property
    def template_renderer(self) -> Renderer:
        return self._cruft_renderer

    @property
    def target_dir(self) -> Path:
        return self.config.inventory.package_dir(self.slug)

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
