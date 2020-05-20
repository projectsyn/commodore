from pathlib import Path as P

import click

from cookiecutter.main import cookiecutter

from . import git
from .dependency_mgmt import create_component_symlinks
from .helpers import yaml_load, yaml_dump


def create_component(config, name, lib, pp):
    component_dir = P('dependencies', name)
    if component_dir.exists():
        raise click.ClickException(
            f"Unable to add component {name}: {component_dir} already exists.")
    click.secho(f"Adding component {name}...", bold=True)
    cookiecutter_args = {
        'component': name,
        'add_lib': 'y' if lib else 'n',
        'add_pp': 'y' if pp else 'n',
    }
    cookiecutter('component-template', no_input=True,
                 output_dir='dependencies',
                 extra_context=cookiecutter_args)

    repo = git.create_repository(component_dir)
    git.add_remote(repo, 'origin', f"{config.global_git_base}/commodore-components/{name}.git")
    index = repo.index
    index.add('*')
    git.commit(repo, 'Initial commit')

    click.echo(' > Installing component')
    create_component_symlinks(config, name)

    targetfile = P('inventory', 'targets', 'cluster.yml')
    target = yaml_load(targetfile)
    target['classes'].append(f"components.{name}")
    target['classes'].insert(0, f"defaults.{name}")
    yaml_dump(target, targetfile)

    click.secho(f"Component {name} successfully added 🎉", bold=True)
