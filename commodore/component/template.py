import datetime

from pathlib import Path as P

import click

from cookiecutter.main import cookiecutter

from commodore import git, __install_dir__
from commodore import config as CommodoreConfig
from commodore.config import Component
from commodore.dependency_mgmt import create_component_symlinks
from commodore.helpers import yaml_load, yaml_dump


class ComponentFactory:
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
    def name(self):
        if not isinstance(self._name, str) or len(self._name) == 0:
            return self.slug
        return self._name

    @name.setter
    def name(self, name):
        self._name = name

    def cookiecutter_args(self):
        return {
            'add_lib': 'y' if self.library else 'n',
            'add_pp': 'y' if self.post_process else 'n',
            'copyright_holder': self.copyright_holder,
            'copyright_year': self.today.strftime("%Y"),
            'github_owner': self.github_owner,
            'name': self.name,
            'slug': self.slug,
            'release_date': self.today.strftime("%Y-%m-%d"),
        }

    def create(self):
        component = Component(
            name=self.slug,
            repo=None,
            version='master',
            repo_url=f"git@github.com:{self.github_owner}/component-{self.slug}.git",
        )
        if component.target_directory.exists():
            raise click.ClickException(
                f"Unable to add component {self.name}: {component.target_directory} already exists.")
        click.secho(f"Adding component {self.name}...", bold=True)
        component_template = __install_dir__ / 'component-template'
        cookiecutter(str(component_template.resolve()), no_input=True,
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
