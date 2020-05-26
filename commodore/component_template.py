from pathlib import Path as P

import click

from cookiecutter.main import cookiecutter

from . import git
from .config import Component
from .dependency_mgmt import create_component_symlinks
from .helpers import yaml_load, yaml_dump


def create_component(config, name, lib, pp):
    component = Component(
        name=name,
        repo=None,
        version='master',
        repo_url=f"{config.default_component_base}/{name}.git",
    )
    if component.target_directory.exists():
        raise click.ClickException(
            f"Unable to add component {name}: {component.target_directory} already exists.")
    click.secho(f"Adding component {name}...", bold=True)
    cookiecutter_args = {
        'component': name,
        'add_lib': 'y' if lib else 'n',
        'add_pp': 'y' if pp else 'n',
    }
    cookiecutter('component-template', no_input=True,
                 output_dir='dependencies',
                 extra_context=cookiecutter_args)

    repo = git.create_repository(component.target_directory)
    component = component._replace(repo=repo)
    git.add_remote(repo, 'origin', component.repo_url)
    index = repo.index
    index.add('*')
    git.commit(repo, 'Initial commit')

    click.echo(' > Installing component')
    create_component_symlinks(config, component)

    targetfile = P('inventory', 'targets', 'cluster.yml')
    target = yaml_load(targetfile)
    target['classes'].append(f"components.{name}")
    target['classes'].insert(0, f"defaults.{name}")
    yaml_dump(target, targetfile)

    click.secho(f"Component {name} successfully added 🎉", bold=True)
