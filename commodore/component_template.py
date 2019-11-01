import click

from cookiecutter.main import cookiecutter
from pathlib import Path as P

from . import git
from .dependency_mgmt import create_component_symlinks
from .helpers import yaml_load, yaml_dump

def create_component(name):
    component_dir = P('dependencies', name)
    if component_dir.exists():
        raise click.ClickException(f"Unable to add component {name}: {component_dir} already exists.")
    click.secho(f"Adding component {name}...", bold=True)
    cookiecutter('component-template', no_input=True,
            output_dir='dependencies', extra_context={ 'component': name })

    repo = git.create_repository(component_dir)
    index = repo.index
    index.add('*')
    index.commit("Initial commit")

    create_component_symlinks(name)

    targetfile = P('inventory','targets','cluster.yml')
    target = yaml_load(targetfile)
    target['classes'].append(f"components.{name}")
    yaml_dump(target, targetfile)

    click.secho(f"Component {name} successfully added 🎉", bold=True)
