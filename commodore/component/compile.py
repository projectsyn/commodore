import os
from pathlib import Path as P
import shutil
import tempfile

import click

from commodore.config import Config
from commodore.dependency_mgmt import fetch_jsonnet_libs, _relsymlink
from commodore.helpers import kapitan_compile


libs = [{'name': 'kube-libsonnet',
                 'repository': 'https://github.com/bitnami-labs/kube-libsonnet',
                 'files': [{'libfile': 'kube.libsonnet',
                            'targetfile': 'kube.libjsonnet'}],
         }]


def compile_component(config: Config, component_path, value_files, search_paths, output_path):
    # Resolve all input to absolute paths to fix symlinks
    component_path = P(component_path).resolve()
    value_files = [P(f).resolve() for f in value_files]
    search_paths = [P(d).resolve() for d in search_paths]
    output_path = P(output_path).resolve()
    # Ignore 'component-' prefix in dir name
    component_name = component_path.stem.replace('component-', '')

    click.secho(f"Compile component {component_name}...", bold=True)

    temp_dir = P(tempfile.mkdtemp(prefix='component-')).resolve()
    original_working_dir = os.getcwd()
    os.chdir(temp_dir)
    try:
        if config.debug:
            click.echo(f"   > Created temp workspace: {temp_dir}")
        for d in ['classes/components', 'classes/defaults', 'targets']:
            os.makedirs(temp_dir / 'inventory' / d, exist_ok=True)
        dependencies_path = temp_dir / 'dependencies'
        dependencies_path.mkdir(exist_ok=True)
        # Create class symlink
        _relsymlink(
            component_class_file.parent,
            component_class_file.name,
            temp_dir / 'inventory/classes/components')
        # Create defaults symlink
        _relsymlink(
            component_defaults_file.parent,
            component_defaults_file.name,
            temp_dir / 'inventory/classes/defaults',
            f"{component_name}.yml")
        # Create component symlink
        _relsymlink(
            component_path.parent,
            component_path.name,
            dependencies_path,
            component_name)
        # Create value symlinks
        for file in value_files:
            _relsymlink(file.parent, file.name, temp_dir / 'inventory/classes')

        # Create class for fake parameters
        with open(temp_dir / 'inventory/classes/fake.yml', 'w') as file:
            file.write("""
parameters:
  cloud:
    provider: cloudscale
    region: rma1
  cluster:
    catalog_url: ssh://git@git.example.com/org/repo.git
    dist: test-distribution
    name: c-green-test-1234
  customer:
    name: t-silent-test-1234
  argocd:
    namespace: test

  kapitan:
    vars:
      target: test
      namespace: test
""")

        # Create test target
        with open(temp_dir / 'inventory/targets/test.yml', 'w') as file:
            value_classes = "\n".join([f"- {c.stem}" for c in value_files])
            file.write(f"""
classes:
- fake
- defaults.{component_name}
- components.{component_name}
{value_classes}
""")

        # Fake Argo CD lib
        (temp_dir / 'dependencies/lib').mkdir(exist_ok=True)
        with open(temp_dir / 'dependencies/lib/argocd.libjsonnet', 'w') as file:
            file.write("""
local ArgoApp(component, namespace, project='', secrets=true) = {};
local ArgoProject(name) = {};

{
  App: ArgoApp,
  Project: ArgoProject,
}
""")

        # Fetch Jsonnet libs
        fetch_jsonnet_libs(config, libs)

        # Compile component
        kapitan_compile(config,
                        target='test',
                        output_dir=output_path,
                        search_paths=search_paths,
                        fake_refs=True,
                        reveal=True)
        click.echo(f" > Component compiled to {output_path / 'compiled/test'}")
    finally:
        os.chdir(original_working_dir)
        if config.trace:
            click.echo(f" > Temp dir left in place {temp_dir}")
        else:
            if config.debug:
                click.echo(f" > Remove temp dir {temp_dir}")
            shutil.rmtree(temp_dir)
