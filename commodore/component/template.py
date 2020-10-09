import datetime

from pathlib import Path as P
from shutil import rmtree

import click
import json
import re

from cookiecutter.main import cookiecutter

from commodore import git, __install_dir__
from commodore import config as CommodoreConfig
from commodore.config import Component
from commodore.dependency_mgmt import (
    create_component_symlinks,
    delete_component_symlinks,
    fetch_jsonnet_libraries,
)

from commodore.helpers import yaml_load, yaml_dump


slug_regex = re.compile("^[a-z][a-z0-9-]+[a-z0-9]$")


class ComponentTemplater:
    # pylint: disable=too-many-instance-attributes
    config: CommodoreConfig
    slug: str
    library: bool
    post_process: bool
    github_owner: str
    copyright_holder: str
    today: datetime

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
        component = Component(
            name=self.slug,
            repo=None,
            version="master",
            repo_url=f"git@github.com:{self.github_owner}/component-{self.slug}.git",
        )
        if component.target_directory.exists():
            raise click.ClickException(
                f"Unable to add component {self.name}: {component.target_directory} already exists."
            )
        click.secho(f"Adding component {self.name}...", bold=True)
        component_template = __install_dir__ / "component-template"
        cookiecutter(
            str(component_template.resolve()),
            no_input=True,
            output_dir="dependencies",
            extra_context=self.cookiecutter_args(),
        )

        repo = git.create_repository(component.target_directory)
        component = component._replace(repo=repo)
        git.add_remote(repo, "origin", component.repo_url)
        index = repo.index
        index.add("*")
        index.add(".github")
        index.add(".gitignore")
        index.add(".*.yml")
        index.add(".editorconfig")
        git.commit(repo, "Initial commit", self.config)

        click.echo(" > Installing component")
        try:
            create_component_symlinks(self.config, component)

            targetfile = P("inventory", "targets", "cluster.yml")
            insert_into_inventory_targets_cluster(targetfile, self.slug)
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
        component = Component(
            name=self.slug,
            repo=None,
            repo_url="",
        )

        if component.target_directory.exists():

            if not self.config.force:
                click.confirm(
                    "Are you sure you want to delete component "
                    f"{self.slug}? This action cannot be undone",
                    abort=True,
                )
            delete_component_symlinks(self.config, component)
            rmtree(component.target_directory)

            targetfile = P("inventory", "targets", "cluster.yml")
            remove_from_inventory_targets_cluster(targetfile, self.slug)
            remove_from_jsonnetfile(P("jsonnetfile.json"), component.target_directory)
            # Fetch jsonnet libs after removing component from jsonnetfile to
            # remove symlink to removed component in vendor/
            fetch_jsonnet_libraries()

            click.secho(f"Component {self.slug} successfully deleted 🎉", bold=True)
        else:
            raise click.BadParameter(
                "Cannot find component with slug " f"'{self.slug}'."
            )


def insert_into_inventory_targets_cluster(targetfile: P, slug: str):
    """
    Insert references to the component identified by the passed-in slug into the
    inventory.
    """
    target = yaml_load(targetfile)
    # Defaults need to be processed first, so we insert them at the head of the
    # list.
    target["classes"].insert(0, f"defaults.{slug}")
    # The component class itself can be added as the last element.
    target["classes"].append(f"components.{slug}")
    yaml_dump(target, targetfile)


def remove_from_inventory_targets_cluster(targetfile: P, slug: str):
    """
    Removed references to the component identified by the passed-in slug from
    the inventory.
    """
    target = yaml_load(targetfile)
    try:
        target["classes"].remove(f"defaults.{slug}")
    except ValueError:
        # That component default is not in the list apparently, it's fine to
        # ignore (it's already in the state we want).
        pass

    try:
        target["classes"].remove(f"components.{slug}")
    except ValueError:
        # Again, if the component already doesn't appear in the list, it's fine
        # to ignore.
        pass

    yaml_dump(target, targetfile)


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
