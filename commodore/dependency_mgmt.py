import os
import json
from pathlib import Path as P
from subprocess import call  # nosec
from typing import Dict

import click

from kapitan.cached import reset_cache as reset_reclass_cache
from kapitan.resources import inventory_reclass

from . import git
from .config import Config
from .component import Component
from .helpers import relsymlink, yaml_load, delsymlink


def create_component_symlinks(cfg, component: Component):
    """
    Create symlinks in the inventory subdirectory.

    The actual code for components lives in the dependencies/ subdirectory, but
    we want to access some of the file contents through the inventory.
    """
    relsymlink(component.class_file, P("inventory/classes/components"))
    relsymlink(
        component.defaults_file,
        P("inventory/classes/defaults"),
        dest_name=f"{component.name}.yml",
    )

    for file in component.lib_files:
        if cfg.debug:
            click.echo(f"     > installing template library: {file}")
        relsymlink(file, P("dependencies/lib"))


def delete_component_symlinks(cfg, component: Component):
    """
    Remove the component symlinks in the inventory subdirectory.

    This is the reverse from the createa_component_symlinks method and is used
    when deleting a component.
    """

    component_class = P(f"inventory/classes/components/{component.name}.yml")
    component_default_class = P(f"inventory/classes/defaults/{component.name}.yml")

    delsymlink(component_class, cfg.debug)
    delsymlink(component_default_class, cfg.debug)

    # If the component has a lib/ subdir, remove the links to the dependencies/lib.
    for file in component.lib_files:
        delsymlink(file, cfg.debug)


def _discover_components(cfg, inventory_path):
    """
    Discover components in `inventory_path/` by extracting all entries from
    the reclass applications dictionary.
    """
    reset_reclass_cache()
    kapitan_applications = inventory_reclass(inventory_path)["applications"]
    components = set()
    for component in kapitan_applications.keys():
        if cfg.debug:
            click.echo(f"   > Found component {component}")
        components.add(component)
    return sorted(components)


def _read_component_urls(cfg: Config, component_names) -> Dict[str, str]:
    component_urls = {}

    if cfg.debug:
        click.echo(f"   > Read commodore config file {cfg.config_file}")
    try:
        commodore_config = yaml_load(cfg.config_file)
    except Exception as e:
        raise click.ClickException(
            f"Could not read Commodore configuration: {e}"
        ) from e

    for component_name in component_names:
        component_urls[
            component_name
        ] = f"{cfg.default_component_base}/{component_name}.git"

    if commodore_config is None:
        click.secho("Empty Commodore config file", fg="yellow")
    else:
        for component_override in commodore_config.get("components", []):
            if cfg.debug:
                click.echo(
                    f"   > Found override for component {component_override['name']}:"
                )
                click.echo(f"     Using URL {component_override['url']}")
            component_urls[component_override["name"]] = component_override["url"]

    return component_urls


def fetch_components(cfg):
    """
    Download all components required by target. Generate list of components
    by searching for classes with prefix `components.` in the inventory files.

    Component repos are searched in `GLOBAL_GIT_BASE/commodore_components`.
    """

    click.secho("Discovering components...", bold=True)
    os.makedirs("inventory/classes/components", exist_ok=True)
    os.makedirs("inventory/classes/defaults", exist_ok=True)
    os.makedirs("dependencies/lib", exist_ok=True)
    component_names = _discover_components(cfg, "inventory")
    urls = _read_component_urls(cfg, component_names)
    click.secho("Fetching components...", bold=True)
    for name, url in urls.items():
        if cfg.debug:
            click.echo(f" > Fetching component {name}...")
        c = Component(name, repo_url=url)
        c.checkout()
        cfg.register_component(c)
        create_component_symlinks(cfg, c)


def set_component_overrides(cfg, versions):
    """
    Set component overrides according to versions and URLs provided in versions dict.
    The dict is assumed to contain the component names as keys, and dicts as
    values. The value dicts are assumed to contain a key 'version' which
    indicates the version as a Git tree-ish. Additionally the key 'url' can
    specify the URL of the Git repo.
    """

    click.secho("Setting component overrides...", bold=True)
    for component_name, overrides in versions.items():
        if component_name not in cfg.get_components():
            continue
        component = cfg.get_components()[component_name]
        needs_checkout = False
        if "url" in overrides:
            url = overrides["url"]
            if cfg.debug:
                click.echo(f" > Set URL for {component.name}: {url}")
            needs_checkout = git.update_remote(component.repo, url)
            component.repo_url = url
        if "version" in overrides:
            component.version = overrides["version"]
            if cfg.debug:
                click.echo(f" > Set version for {component.name}: {component.version}")
            needs_checkout = True
        if needs_checkout:
            try:
                git.checkout_version(component.repo, component.version)
            except git.RefError as e:
                raise click.ClickException(
                    f"While setting component override: {e}"
                ) from e
            # Create symlinks again with correctly checked out components
            create_component_symlinks(cfg, component)


def fetch_jsonnet_libs(config, libs):
    """
    Download all libraries specified in list `libs`.
    Each entry in `libs` is assumed to be a dict with keys
      * 'repository', the value of which is interpreted as a git repository to
                      clone.
      * 'files', a list of dicts which defines which files in the repository
                 should be installed as template libraries.
    Each entry in files is assumed to have the keys
      * 'libfile', indicating a filename relative to the repository of the
                   library to install
      * 'targetfile', the file name to use as the symlink target when
                      installing the library
    """

    click.secho("Updating Jsonnet libraries...", bold=True)
    os.makedirs("dependencies/libs", exist_ok=True)
    os.makedirs("dependencies/lib", exist_ok=True)
    for lib in libs:
        libname = lib["name"]
        filestext = " ".join([f["targetfile"] for f in lib["files"]])
        if config.debug:
            click.echo(f" > {libname}: {filestext}")
        repo = git.clone_repository(
            lib["repository"], P("dependencies/libs") / libname, config
        )
        for file in lib["files"]:
            relsymlink(
                P(repo.working_tree_dir) / file["libfile"],
                P("dependencies/lib"),
                dest_name=file["targetfile"],
            )


def write_jsonnetfile(config: Config):
    """
    Writes the file `jsonnetfile.json` containing all components as local dependencies.
    """

    dependencies = []

    for component in config.get_components().values():
        dependencies.append(
            {
                "source": {
                    "local": {
                        "directory": str(component.target_directory),
                    }
                }
            }
        )

    # Defining the `lib` folder as a local dependency is just a cheap way to have a symlink to that folder.
    dependencies.append(
        {
            "source": {
                "local": {
                    "directory": "dependencies/lib",
                }
            }
        }
    )

    jsonnetfile = {
        "version": 1,
        "dependencies": dependencies,
        "legacyImports": True,
    }

    with open("jsonnetfile.json", "w") as file:
        file.write(json.dumps(jsonnetfile, indent=4))


def fetch_jsonnet_libraries(cwd: P = None):
    """
    Download Jsonnet libraries using Jsonnet-Bundler.
    """

    try:
        # To make sure we don't use any stale lock files
        lock_file = P("jsonnetfile.lock.json")
        if lock_file.exists():
            lock_file.unlink()
        if call(["jb", "install"], cwd=cwd) != 0:
            raise click.ClickException("jsonnet-bundler exited with error")
    except FileNotFoundError as e:
        raise click.ClickException(
            "the jsonnet-bundler executable `jb` could not be found"
        ) from e


def register_components(cfg: Config):
    """
    Register all components which are currently checked out in dependencies/
    in the Commodore config.
    """
    click.secho("Registering components...", bold=True)
    for c in P("dependencies").iterdir():
        # Skip jsonnet libs when collecting components
        if c.name == "lib" or c.name == "libs":
            continue
        if cfg.debug:
            click.echo(f" > {c}")
        component = Component(c.name)
        cfg.register_component(component)
