import datetime
import json
import os
import re

from pathlib import Path as P
from shutil import rmtree

import click

from cookiecutter.main import cookiecutter

from commodore import git, __install_dir__
from commodore import config as CommodoreConfig
from commodore.component import Component, component_dir
from commodore.cluster import update_target
from commodore.dependency_mgmt import (
    create_component_symlinks,
    delete_component_symlinks,
    fetch_jsonnet_libraries,
    register_components,
)
from commodore.inventory import Inventory

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
            output_dir="dependencies",
            extra_context=self.cookiecutter_args(),
        )

        component = Component(
            self.slug,
            work_dir=self.config.work_dir,
            repo_url=f"git@github.com:{self.github_owner}/component-{self.slug}.git",
            force_init=True,
        )

        repo = component.repo
        index = repo.index
        index.add("*")
        index.add(".github")
        index.add(".gitignore")
        index.add(".*.yml")
        index.add(".editorconfig")
        git.commit(repo, "Initial commit", self.config)

        register_components(self.config)
        self.config.register_component(component)

        click.echo(" > Installing component")
        try:
            create_component_symlinks(self.config, component)
            update_target(self.config, self.slug)
            insert_into_jsonnetfile(P("jsonnetfile.json"), component.target_directory)
            # call fetch_jsonnet_libraries after updating jsonnetfile to
            # symlink new component into vendor/
            fetch_jsonnet_libraries()
        except FileNotFoundError:
            # TODO: This should maybe cleanup the "dependencies" subdirectory
            # (since we just created it).
            click.echo(
                "Cannot find catalog files. Did you forget to run "
                "'catalog compile' in the current directory?"
            )
        else:
            click.secho(f"Component {self.name} successfully added 🎉", bold=True)

    def delete(self):
        inv = Inventory()
        if component_dir(self.config.work_dir, self.slug).exists():
            component = Component(self.slug, work_dir=self.config.work_dir)

            if not self.config.force:
                click.confirm(
                    "Are you sure you want to delete component "
                    f"{self.slug}? This action cannot be undone",
                    abort=True,
                )
            delete_component_symlinks(self.config, component)
            rmtree(component.target_directory)

            os.unlink(inv.target_file(component))
            remove_from_jsonnetfile(P("jsonnetfile.json"), component.target_directory)
            # Fetch jsonnet libs after removing component from jsonnetfile to
            # remove symlink to removed component in vendor/
            fetch_jsonnet_libraries()

            click.secho(f"Component {self.slug} successfully deleted 🎉", bold=True)
        else:
            raise click.BadParameter(
                "Cannot find component with slug " f"'{self.slug}'."
            )


def insert_into_jsonnetfile(jsonnetfile: P, componentdir: P):
    """
    Insert new component into jsonnetfile
    """
    with open(jsonnetfile, "r") as jf:
        jsonnetf = json.load(jf)

    jsonnetf["dependencies"].append(
        {"source": {"local": {"directory": str(componentdir)}}}
    )

    with open(jsonnetfile, "w") as jf:
        json.dump(jsonnetf, jf, indent=4)


def remove_from_jsonnetfile(jsonnetfile: P, componentdir: P):
    """
    Remove component from jsonnetfile
    """
    with open(jsonnetfile, "r") as jf:
        jsonnetf = json.load(jf)

    deps = jsonnetf["dependencies"]
    deps = list(
        filter(
            lambda d: d.get("source", {}).get("local", {}).get("directory", {})
            != str(componentdir),
            deps,
        )
    )
    jsonnetf["dependencies"] = deps
    with open(jsonnetfile, "w") as jf:
        json.dump(jsonnetf, jf, indent=4)
