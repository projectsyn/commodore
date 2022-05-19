from __future__ import annotations

from pathlib import Path
from shutil import rmtree
from typing import Sequence

import click

from cookiecutter.main import cookiecutter

from commodore import __install_dir__
from commodore.component import Component, component_dir
from commodore.dependency_templater import Templater, Renderer


class ComponentTemplater(Templater):
    library: bool
    post_process: bool
    matrix_tests: bool

    @property
    def cookiecutter_args(self) -> dict[str, str]:
        return {
            "add_lib": "y" if self.library else "n",
            "add_pp": "y" if self.post_process else "n",
            "add_golden": "y" if self.golden_tests else "n",
            "add_matrix": "y" if self.matrix_tests else "n",
            "copyright_holder": self.copyright_holder,
            "copyright_year": self.today.strftime("%Y"),
            "github_owner": self.github_owner,
            "name": self.name,
            "slug": self.slug,
            "release_date": self.today.strftime("%Y-%m-%d"),
        }

    @property
    def target_dir(self) -> Path:
        return component_dir(self.config.work_dir, self.slug)

    @property
    def template(self) -> str:
        component_template = __install_dir__ / "component-template"
        return str(component_template.resolve())

    @property
    def deptype(self) -> str:
        return "component"

    @property
    def template_renderer(self) -> Renderer:
        return cookiecutter

    @property
    def repo_url(self) -> str:
        return f"git@github.com:{self.github_owner}/component-{self.slug}.git"

    @property
    def additional_files(self) -> Sequence[str]:
        return [
            ".github",
            ".gitignore",
            ".*.yml",
            ".editorconfig",
        ]

    def delete(self):
        if component_dir(self.config.work_dir, self.slug).exists():
            component = Component(self.slug, work_dir=self.config.work_dir)

            if not self.config.force:
                click.confirm(
                    "Are you sure you want to delete component "
                    f"{self.slug}? This action cannot be undone",
                    abort=True,
                )
            rmtree(component.target_directory)

            click.secho(f"Component {self.slug} successfully deleted 🎉", bold=True)
        else:
            raise click.BadParameter(
                "Cannot find component with slug " f"'{self.slug}'."
            )
