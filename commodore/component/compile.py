from pathlib import Path as P
import shutil
import tempfile
from textwrap import dedent

import click
from kapitan.resources import inventory_reclass

from commodore.config import Config
from commodore.component import Component
from commodore.dependency_mgmt import (
    fetch_jsonnet_libraries,
    validate_component_library_name,
    create_component_library_aliases,
)
from commodore.helpers import kapitan_compile, relsymlink
from commodore.inventory import Inventory
from commodore.postprocess import postprocess_components


# pylint: disable=too-many-arguments disable=too-many-locals disable=too-many-statements
def compile_component(
    config: Config,
    component_path,
    instance_name,
    value_files,
    search_paths,
    output_path,
):
    # Resolve all input to absolute paths to fix symlinks
    component_path = P(component_path).resolve()
    value_files = [P(f).resolve() for f in value_files]
    search_paths = [P(d).resolve() for d in search_paths]
    search_paths.append(component_path / "vendor")
    output_path = P(output_path).resolve()
    # Ignore 'component-' prefix in dir name
    component_name = component_path.stem.replace("component-", "")

    # Fall back to `component as component` when instance_name is empty
    if instance_name is None or instance_name == "":
        instance_name = component_name
        click.secho(f"Compile component {component_name}...", bold=True)
    else:
        click.secho(
            f"Compile component {component_name} as {instance_name}...", bold=True
        )

    temp_dir = P(tempfile.mkdtemp(prefix="component-")).resolve()
    config.work_dir = temp_dir
    try:
        if config.debug:
            click.echo(f"   > Created temp workspace: {config.work_dir}")
        inv = config.inventory
        inv.ensure_dirs()
        search_paths.append(inv.dependencies_dir)
        component = Component(component_name, directory=component_path)
        config.register_component(component)
        config.register_component_aliases({instance_name: component_name})
        _prepare_fake_inventory(inv, component, value_files)

        # Validate component libraries
        for lib in component.lib_files:
            validate_component_library_name(config, component.name, lib)

        # Create class for fake parameters
        with open(inv.params_file, "w", encoding="utf-8") as file:
            file.write(
                dedent(
                    f"""
                parameters:
                  cloud:
                    provider: ${{facts:cloud}}
                    region: ${{facts:region}}
                  cluster:
                    catalog_url: ssh://git@git.example.com/org/repo.git
                    dist: test-distribution
                    name: c-green-test-1234
                    tenant: t-silent-test-1234
                  customer:
                    name: ${{cluster:tenant}}
                  facts:
                    distribution: test-distribution
                    cloud: cloudscale
                    region: rma1
                  argocd:
                    namespace: test
                  components:
                    {component.name}:
                      url: https://example.com/{component.name}.git
                      version: master

                  kapitan:
                    vars:
                        target: {instance_name}
                        namespace: test"""
                )
            )

        # Create test target
        with open(inv.target_file(instance_name), "w", encoding="utf-8") as file:
            value_classes = "\n".join([f"- {c.stem}" for c in value_files])
            file.write(
                dedent(
                    f"""
                classes:
                - params.{inv.bootstrap_target}
                - defaults.{component_name}
                - components.{component_name}
                {value_classes}
                parameters:
                  _instance: {instance_name}
                  _base_directory: {str(component.target_directory)}
                """
                )
            )

        # Fake Argo CD lib
        # We plug "fake" Argo CD library here because every component relies on it
        # and we don't want to provide it every time when compiling a single component.
        with open(inv.lib_dir / "argocd.libjsonnet", "w", encoding="utf-8") as file:
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

        # Verify component alias
        nodes = inventory_reclass(inv.inventory_dir)["nodes"]
        config.verify_component_aliases(nodes[instance_name]["parameters"])

        cluster_params = nodes[instance_name]["parameters"]
        create_component_library_aliases(config, cluster_params)

        # Render jsonnetfile.jsonnet if necessary
        component_params = nodes[instance_name]["parameters"].get(
            component_name.replace("-", "_"), {}
        )
        component.render_jsonnetfile_json(component_params)
        # Fetch Jsonnet libs
        fetch_jsonnet_libraries(component_path)

        # Compile component
        kapitan_compile(
            config,
            [instance_name],
            output_dir=output_path,
            search_paths=search_paths,
            fake_refs=True,
            reveal=True,
        )
        click.echo(
            f" > Component compiled to {output_path / 'compiled' / instance_name}"
        )

        # prepare inventory and fake component object for postprocess
        config.work_dir = output_path
        postprocess_components(config, nodes, config.get_components())
        config.print_deprecation_notices()
    finally:
        if config.trace:
            click.echo(f" > Temp dir left in place {temp_dir}")
        else:
            if config.debug:
                click.echo(f" > Remove temp dir {temp_dir}")
            shutil.rmtree(temp_dir)


def _prepare_fake_inventory(inv: Inventory, component: Component, value_files):
    component_class_file = component.class_file
    component_defaults_file = component.defaults_file
    if not component_class_file.exists():
        raise click.ClickException(
            f"Could not find component class file: {component_class_file}"
        )
    if not component_defaults_file.exists():
        raise click.ClickException(
            f"Could not find component default file: {component_defaults_file}"
        )

    # Create class symlink
    relsymlink(component_class_file, inv.components_dir)
    # Create defaults symlink
    relsymlink(
        component_defaults_file,
        inv.defaults_dir,
        dest_name=f"{component.name}.yml",
    )
    # Create component symlink
    relsymlink(component.target_directory, inv.dependencies_dir, component.name)
    # Create value symlinks
    for file in value_files:
        relsymlink(file.parent / file.name, inv.classes_dir)
