import os
from pathlib import Path as P
import shutil
import tempfile
from textwrap import dedent

import click

from commodore.config import Config, Component
from commodore.dependency_mgmt import fetch_jsonnet_libs, fetch_jsonnet_libraries
from commodore.helpers import kapitan_compile, relsymlink
from commodore.postprocess import postprocess_components
from git import Repo
from kapitan.resources import inventory_reclass


libs = [
    {
        "name": "kube-libsonnet",
        "repository": "https://github.com/bitnami-labs/kube-libsonnet",
        "files": [{"libfile": "kube.libsonnet", "targetfile": "kube.libjsonnet"}],
    }
]


def compile_component(
    config: Config, component_path, value_files, search_paths, output_path
):
    # Resolve all input to absolute paths to fix symlinks
    component_path = P(component_path).resolve()
    value_files = [P(f).resolve() for f in value_files]
    search_paths = [P(d).resolve() for d in search_paths]
    search_paths.append("./dependencies/")
    search_paths.append(component_path / "vendor")
    output_path = P(output_path, "standalone").resolve()
    # Ignore 'component-' prefix in dir name
    component_name = component_path.stem.replace("component-", "")

    click.secho(f"Compile component {component_name}...", bold=True)

    temp_dir = P(tempfile.mkdtemp(prefix="component-")).resolve()
    original_working_dir = os.getcwd()
    os.chdir(temp_dir)
    try:
        if config.debug:
            click.echo(f"   > Created temp workspace: {temp_dir}")

        _prepare_fake_inventory(temp_dir, component_name, component_path, value_files)

        # Create class for fake parameters
        with open(temp_dir / "inventory/classes/fake.yml", "w") as file:
            file.write(
                dedent(
                    f"""
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
                        target: {component_name}
                        namespace: test"""
                )
            )

        # Create test target
        with open(temp_dir / f"inventory/targets/{component_name}.yml", "w") as file:
            value_classes = "\n".join([f"- {c.stem}" for c in value_files])
            file.write(
                dedent(
                    f"""
                classes:
                - fake
                - defaults.{component_name}
                - components.{component_name}
                {value_classes}"""
                )
            )

        # Fake Argo CD lib
        # We plug "fake" Argo CD library here because every component relies on it
        # and we don't want to provide it every time when compiling a single component.
        (temp_dir / "dependencies/lib").mkdir(exist_ok=True)
        with open(temp_dir / "dependencies/lib/argocd.libjsonnet", "w") as file:
            file.write(
                dedent(
                    """
                local ArgoApp(component, namespace, project='', secrets=true) = {};
                local ArgoProject(name) = {};

                {
                  App: ArgoApp,
                  Project: ArgoProject,
                }"""
                )
            )

        # Fetch Jsonnet libs
        fetch_jsonnet_libs(config, libs)
        if (component_path / "jsonnetfile.json").exists():
            fetch_jsonnet_libraries(component_path)

        # Compile component
        kapitan_compile(
            config,
            [component_name],
            output_dir=output_path,
            search_paths=search_paths,
            fake_refs=True,
            reveal=True,
        )
        click.echo(
            f" > Component compiled to {output_path / 'compiled' / component_name}"
        )

        # prepare inventory and fake component object for postprocess
        inventory = inventory_reclass(temp_dir / "inventory")["nodes"]
        component = Component(
            component_name, Repo(component_path), "https://fake.repo.url/", "master"
        )
        config.register_component(component)
        # We change the working directory to the output_path directory here,
        # as postprocess expects to find `compiled/<target>` in the working
        # directory.
        os.chdir(output_path)
        postprocess_components(config, inventory, config.get_components())
    finally:
        os.chdir(original_working_dir)
        if config.trace:
            click.echo(f" > Temp dir left in place {temp_dir}")
        else:
            if config.debug:
                click.echo(f" > Remove temp dir {temp_dir}")
            shutil.rmtree(temp_dir)


def _prepare_fake_inventory(temp_dir: P, component_name, component_path, value_files):
    component_class_file = component_path / "class" / f"{component_name}.yml"
    component_defaults_file = component_path / "class" / "defaults.yml"
    if not component_class_file.exists():
        raise click.ClickException(
            f"Could not find component class file: {component_class_file}"
        )
    if not component_defaults_file.exists():
        raise click.ClickException(
            f"Could not find component default file: {component_defaults_file}"
        )

    for d in ["classes/components", "classes/defaults", "targets"]:
        os.makedirs(temp_dir / "inventory" / d, exist_ok=True)
    dependencies_path = temp_dir / "dependencies"
    dependencies_path.mkdir(exist_ok=True)
    # Create class symlink
    relsymlink(
        component_class_file.parent,
        component_class_file.name,
        temp_dir / "inventory/classes/components",
    )
    # Create defaults symlink
    relsymlink(
        component_defaults_file.parent,
        component_defaults_file.name,
        temp_dir / "inventory/classes/defaults",
        f"{component_name}.yml",
    )
    # Create component symlink
    relsymlink(
        component_path.parent, component_path.name, dependencies_path, component_name
    )
    # Create value symlinks
    for file in value_files:
        relsymlink(file.parent, file.name, temp_dir / "inventory/classes")
