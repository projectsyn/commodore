import datetime
import re

from shutil import rmtree

import click

from cookiecutter.main import cookiecutter

from commodore import __install_dir__
from commodore import config as CommodoreConfig
from commodore.component import Component, component_dir

slug_regex = re.compile("^[a-z][a-z0-9-]+[a-z0-9]$")


class ComponentTemplater:
    # pylint: disable=too-many-instance-attributes
    config: CommodoreConfig.Config
    _slug: str
    library: bool
    post_process: bool
    github_owner: str
    copyright_holder: str
    today: datetime.date
    golden_tests: bool
    matrix_tests: bool

    def __init__(self, config, slug):
        self.config = config
        self.slug = slug
        self.today = datetime.date.today()

    @property
    def slug(self):
        return self._slug

    @slug.setter
    def slug(self, slug):
        if slug.startswith("component-"):
            raise click.ClickException(
                'The component slug may not start with "component-"'
            )
        if not slug_regex.match(slug):
            raise click.ClickException(
                f"The component slug must match '{slug_regex.pattern}'"
            )
        self._slug = slug

    @property
    def name(self):
        if not self._name:
            return self.slug
        return self._name

    @name.setter
    def name(self, name):
        self._name = name

    def cookiecutter_args(self):
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

    def create(self):
        path = component_dir(self.config.work_dir, self.slug)
        if path.exists():
            raise click.ClickException(
                f"Unable to add component {self.name}: {path} already exists."
            )

        click.secho(f"Adding component {self.name}...", bold=True)
        component_template = __install_dir__ / "component-template"
        cookiecutter(
            str(component_template.resolve()),
            no_input=True,
            output_dir=self.config.work_dir / "dependencies",
            extra_context=self.cookiecutter_args(),
        )

        component = Component(
            self.slug,
            work_dir=self.config.work_dir,
            repo_url=f"git@github.com:{self.github_owner}/component-{self.slug}.git",
            force_init=True,
        )

        component.repo.stage_all()
        component.repo.stage_files(
            [
                ".github",
                ".gitignore",
                ".*.yml",
                ".editorconfig",
            ]
        )
        component.repo.commit("Initial commit")

        click.secho(f"Component {self.name} successfully added 🎉", bold=True)

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
