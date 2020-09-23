import os
import json
from pathlib import Path as P
from subprocess import call  # nosec

import click

from kapitan.cached import reset_cache as reset_reclass_cache
from kapitan.resources import inventory_reclass

from . import git
from .config import Component, Config
from .helpers import relsymlink, yaml_load, delsymlink


def create_component_symlinks(cfg, component: Component):
    """
    Create symlinks in the inventory subdirectory.

    The actual code for components lives in the dependencies/ subdirectory, but
    we want to access some of the file contents through the inventory.
    """
    relsymlink(component.target_directory / 'class', f"{component.name}.yml",
               'inventory/classes/components')
    component_defaults_class = component.target_directory / 'class' / 'defaults.yml'
    if component_defaults_class.is_file():
        relsymlink(component.target_directory / 'class', 'defaults.yml',
                   P('inventory/classes/defaults'), destname=f"{component.name}.yml")
    else:
        click.secho('     > Old-style component detected. Please move ' +
                    'component defaults to \'class/defaults.yml\'', fg='yellow')
    libdir = component.target_directory / 'lib'
    if libdir.is_dir():
        for file in os.listdir(libdir):
            if cfg.debug:
                click.echo(f"     > installing template library: {file}")
            relsymlink(libdir, file, 'dependencies/lib')


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
    libdir = component.target_directory / 'lib'

    if libdir.is_dir():
        for f in os.listdir(libdir):
            delsymlink(P(f), cfg.debug)


def _discover_components(cfg, inventory_path):
    """
    Discover components in `inventory_path/`. Parse all classes found in
    inventory_path and look for class includes starting with `components.`.
    """
    reset_reclass_cache()
    kapitan_inventory = inventory_reclass(inventory_path, ignore_class_notfound=True)['nodes']['cluster']
    components = set()
    for kls in kapitan_inventory['classes']:
        if kls.startswith('components.'):
            component = kls.split('.')[1]
            if cfg.debug:
                click.echo(f"   > Found component {component}")
            components.add(component)
    return sorted(components)


def _read_component_urls(cfg, component_names):
    components = []
    component_urls = {}
    if cfg.debug:
        click.echo(f"   > Read commodore config file {cfg.config_file}")
    try:
        commodore_config = yaml_load(cfg.config_file)
    except Exception as e:
        raise click.ClickException(f"Could not read Commodore configuration: {e}") from e
    if commodore_config is None:
        click.secho('Empty Commodore config file', fg='yellow')
    else:
        for component_override in commodore_config.get('components', []):
            if cfg.debug:
                click.echo(f"   > Found override for component {component_override['name']}:")
                click.echo(f"     Using URL {component_override['url']}")
            component_urls[component_override['name']] = component_override['url']
    for component_name in component_names:
        repository_url = \
            component_urls.get(
                component_name,
                f"{cfg.default_component_base}/{component_name}.git")
        component = Component(
            name=component_name,
            repo=None,
            version='master',
            repo_url=repository_url,
        )
        components.append(component)
    return components


def fetch_components(cfg):
    """
    Download all components required by target. Generate list of components
    by searching for classes with prefix `components.` in the inventory files.

    Component repos are searched in `GLOBAL_GIT_BASE/commodore_components`.
    """

    click.secho('Discovering components...', bold=True)
    os.makedirs('inventory/classes/components', exist_ok=True)
    os.makedirs('inventory/classes/defaults', exist_ok=True)
    os.makedirs('dependencies/lib', exist_ok=True)
    component_names = _discover_components(cfg, 'inventory')
    components = _read_component_urls(cfg, component_names)
    click.secho('Fetching components...', bold=True)
    for c in components:
        if cfg.debug:
            click.echo(f" > Fetching component {c.name}...")
        repo = git.clone_repository(c.repo_url, c.target_directory, cfg)
        c = c._replace(repo=repo)
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

    click.secho('Setting component overrides...', bold=True)
    for component_name, overrides in versions.items():
        if component_name not in cfg.get_components():
            continue
        component = cfg.get_components()[component_name]
        needs_checkout = False
        if 'url' in overrides:
            url = overrides['url']
            if cfg.debug:
                click.echo(f" > Set URL for {component.name}: {url}")
            needs_checkout = git.update_remote(component.repo, url)
            component = cfg.set_repo_url(component_name, url)
        if 'version' in overrides:
            version = overrides['version']
            if cfg.debug:
                click.echo(f" > Set version for {component.name}: {version}")
            needs_checkout = True
            component = cfg.set_component_version(component_name, version)
        if needs_checkout:
            try:
                git.checkout_version(component.repo, component.version)
            except git.RefError as e:
                raise click.ClickException(f"While setting component override: {e}") from e
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

    click.secho('Updating Jsonnet libraries...', bold=True)
    os.makedirs('dependencies/libs', exist_ok=True)
    os.makedirs('dependencies/lib', exist_ok=True)
    for lib in libs:
        libname = lib['name']
        filestext = ' '.join([f['targetfile'] for f in lib['files']])
        if config.debug:
            click.echo(f" > {libname}: {filestext}")
        repo = git.clone_repository(lib['repository'],
                                    P('dependencies/libs') / libname,
                                    config)
        for file in lib['files']:
            relsymlink(repo.working_tree_dir, file['libfile'],
                       'dependencies/lib', destname=file['targetfile'])


def fetch_jsonnet_libraries(config: Config):
    """
    Download Jsonnet libraries using Jsonnet-Bundler.
    """

    dependencies = []

    for component in config.get_components().values():
        dependencies.append({
            "source": {
                "local": {
                    "directory": str(component.target_directory),
                }
            }
        })

    jsonnetfile = {
        "version": 1,
        "dependencies": dependencies,
        "legacyImports": True,
    }

    with open("jsonnetfile.json", "w") as file:
        file.write(json.dumps(jsonnetfile, indent=4))

    try:
        if call(['jb', 'install']) != 0:
            raise click.ClickException('jsonnet-bundler exited with error')
    except FileNotFoundError as e:
        raise click.ClickException('the jsonnet-bundler executable `jb` could not be found') from e
