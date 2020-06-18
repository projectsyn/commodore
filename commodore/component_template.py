import datetime

from pathlib import Path as P

import click

from cookiecutter.main import cookiecutter

from . import git
from . import config as CommodoreConfig
from .config import Component
from .dependency_mgmt import create_component_symlinks
from .helpers import yaml_load, yaml_dump


class ComponentFactory:
    # pylint: disable=too-many-instance-attributes
    config: CommodoreConfig
    name: str
    slug: str
    library: bool
    post_process: bool
    github_owner: str
    copyright_holder: str
    today: datetime

    def __init__(self, config, name):
        self.config = config
        self.name = name
        self.slug = name.lower().replace(' ', '-')
        self.today = datetime.date.today()

    def cookiecutter_args(self):
        return {
            'add_lib': 'y' if self.library else 'n',
            'add_pp': 'y' if self.post_process else 'n',
            'copyright_holder': self.copyright_holder,
            'copyright_year': self.today.strftime("%Y"),
            'github_owner': self.github_owner,
            'name': self.name,
            'release_date': self.today.strftime("%Y-%m-%d"),
        }

    def create(self):
        component = Component(
            name=self.slug,
            repo=None,
            version='master',
            repo_url=f"git@github.com:{self.github_owner}/compontent-{self.slug}.git",
        )
        if component.target_directory.exists():
            raise click.ClickException(
                f"Unable to add component {self.name}: {component.target_directory} already exists.")
        click.secho(f"Adding component {self.name}...", bold=True)
        cookiecutter('component-template', no_input=True,
                     output_dir='dependencies',
                     extra_context=self.cookiecutter_args())

        repo = git.create_repository(component.target_directory)
        component = component._replace(repo=repo)
        git.add_remote(repo, 'origin', component.repo_url)
        index = repo.index
        index.add('*')
        index.add('.github')
        index.add('.*.yml')
        git.commit(repo, 'Initial commit')

        click.echo(' > Installing component')
        create_component_symlinks(self.config, component)

        targetfile = P('inventory', 'targets', 'cluster.yml')
        target = yaml_load(targetfile)
        target['classes'].append(f"components.{self.slug}")
        target['classes'].insert(0, f"defaults.{self.slug}")
        yaml_dump(target, targetfile)

        click.secho(f"Component {self.name} successfully added 🎉", bold=True)
