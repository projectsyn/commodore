from __future__ import annotations

import shutil
import tempfile

from collections.abc import Iterable
from pathlib import Path as P
from textwrap import dedent
from typing import Optional

import click
import git
from kapitan.resources import inventory_reclass

from commodore.cluster import generate_target
from commodore.config import Config
from commodore.component import Component
from commodore.dependency_mgmt.component_library import (
    validate_component_library_name,
    create_component_library_aliases,
)
from commodore.dependency_mgmt.jsonnet_bundler import fetch_jsonnet_libraries
from commodore.helpers import kapitan_compile, relsymlink, yaml_dump
from commodore.inventory import Inventory
from commodore.inventory.lint import check_removed_reclass_variables
from commodore.postprocess import postprocess_components


# pylint: disable=too-many-arguments disable=too-many-locals
def compile_component(
    config: Config,
    component_path_: str,
    instance_name_: Optional[str],
    value_files_: Iterable[str],
    search_paths_: Iterable[str],
    output_path_: str,
    component_name: str,
):
    # Resolve all input to absolute paths to fix symlinks
    component_path = P(component_path_).resolve()
    value_files = [P(f).resolve() for f in value_files_]
    search_paths = [P(d).resolve() for d in search_paths_]
    search_paths.append(component_path / "vendor")
    output_path = P(output_path_).resolve()

    if not component_name:
        # Ignore 'component-' prefix in repo name, this assumes that the repo name
        # indicates the component name for components in subpaths.
        component_name = component_path.stem.replace("component-", "")

    # Fall back to `component as component` when instance_name is empty
    if instance_name_ is None or instance_name_ == "":
        instance_name = component_name
        click.secho(f"Compile component {component_name}...", bold=True)
    else:
        instance_name = instance_name_
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
        component = _setup_component(
            config,
            component_name,
            instance_name,
            component_path,
        )
        _prepare_kapitan_inventory(inv, component, value_files, instance_name)

        # Raise error if component uses removed reclass parameters
        check_removed_reclass_variables(
            config,
            "component",
            [component.defaults_file, component.class_file] + value_files,
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

        # Change working directory for postprocessing
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


def _setup_component(
    config: Config,
    component_name: str,
    instance_name: str,
    component_path: P,
) -> Component:
    if not component_path.is_dir():
        raise click.ClickException(
            f"Can't compile component, repository {component_path} doesn't exist"
        )
    # Search for git repo in parents, this is necessary when compiling a component in a
    # repo subdirectory.
    try:
        cr = git.Repo(component_path, search_parent_directories=True)
        if not cr.working_tree_dir:
            raise click.ClickException(
                f"Can't compile component, repository {component_path} doesn't exist"
            )
        target_dir = P(cr.working_tree_dir)
        # compute subpath from Repo working tree dir and component path
        sub_path = str(component_path.absolute().relative_to(target_dir))
    except git.InvalidGitRepositoryError:
        click.echo(" > Couldn't determine Git repository for component")
        # Just treat `component_path` as a directory holding a component, don't care
        # about Git repo details here.
        target_dir = component_path
        sub_path = ""

    component = Component(
        component_name,
        None,
        # Use repo working tree as component "target directory", otherwise we get messy
        # results with duplicate subpaths.
        directory=target_dir,
        # Use computed subpath to ensure we accurately replicate the environment in
        # which the component will be compiled in a cluster catalog.
        sub_path=sub_path,
    )
    config.register_component(component)
    config.register_component_aliases({instance_name: component_name})

    # Validate component libraries
    for lib in component.lib_files:
        validate_component_library_name(component.name, lib)

    return component


def _prepare_kapitan_inventory(
    inv: Inventory, component: Component, value_files: Iterable[P], instance_name: str
):
    """
    Setup Kapitan inventory.

    Create component symlinks, values file symlinks, setup params class with fake values
    and Kapitan target for the component, create a fake `lib/argocd.libjsonnet`.
    """
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

    # Create class for fake parameters
    yaml_dump(
        {
            "parameters": {
                "cluster": {
                    "catalog_url": "ssh://git@git.example.com/org/repo.git",
                    "name": "c-green-test-1234",
                    "display_name": "Test Cluster 1234",
                    "tenant": "t-silent-test-1234",
                    "tenant_display_name": "Test Tenant 1234",
                },
                "facts": {
                    "distribution": "test-distribution",
                    "cloud": "cloudscale",
                    "region": "rma1",
                },
                "argocd": {
                    "namespace": "test",
                },
                "components": {
                    component.name: {
                        "url": f"https://example.com/{component.name}.git",
                        "version": "master",
                    }
                },
                "kapitan": {
                    "vars": {
                        "target": instance_name,
                    },
                    "namespace": "test",
                },
            }
        },
        inv.params_file,
    )

    # Create test target
    value_classes = [f"{c.stem}" for c in value_files]
    classes = [
        f"params.{inv.bootstrap_target}",
        f"defaults.{component.name}",
        f"components.{component.name}",
    ] + value_classes
    yaml_dump(
        generate_target(
            inv, instance_name, {component.name: component}, classes, component.name
        ),
        inv.target_file(instance_name),
    )

    # Fake Argo CD lib
    # We plug "fake" Argo CD library here because every component relies on it
    # and we don't want to provide it every time when compiling a single component.
    with open(inv.lib_dir / "argocd.libjsonnet", "w", encoding="utf-8") as argocd_libf:
        argocd_libf.write(
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
