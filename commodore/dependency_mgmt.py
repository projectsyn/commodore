import click, os

from . import git

def _relsymlink(srcdir, srcname, destdir, destname=None):
    if destname is None:
        destname = srcname
    link_src = os.path.relpath(f"{srcdir}/{srcname}", start=destdir)
    os.symlink(link_src, f"{destdir}/{destname}")

def _fetch_component(cfg, component):
    repository_url = f"{cfg.global_git_base}/commodore-components/{component}.git"
    target_directory = f"dependencies/{component}"
    repo = git.clone_repository(repository_url, target_directory)
    cfg.register_component(component, repo)
    _relsymlink(f"{target_directory}/class", f"{component}.yml",
                "inventory/classes/components")
    libdir = f"{target_directory}/lib"
    if os.path.isdir(libdir):
        for file in os.listdir(libdir):
            click.echo(f"     > installing template library: {file}")
            _relsymlink(f"{target_directory}/lib", file, "dependencies/lib")

def fetch_components(cfg, components):
    """
    Download all components specified in argument `components`.
    Components are searched in
    `GLOBAL_GIT_BASE/commodore_components/{component-name}.git`.
    """

    os.makedirs('inventory/classes/components', exist_ok=True)
    os.makedirs('dependencies/lib', exist_ok=True)
    click.secho("Updating components...", bold=True)
    for c in components:
        click.echo(f" > {c}...")
        _fetch_component(cfg, c)

def _set_component_version(cfg, component, version):
    click.echo(f" > {component}: {version}")
    try:
        git.checkout_version(cfg.get_component_repo(component), version)
    except git.RefError as e:
        click.secho(f"    unable to set version: {e}", fg='yellow')
    cfg.set_component_version(component, version)

def set_component_versions(cfg, versions):
    """
    Set component versions according to versions provided in versions dict.
    The dict is assumed to contain component names as keys, and dicts as
    values. The value dicts are assumed to contain a key 'version' which
    indicates the version as a Git tree-ish.
    """

    click.secho("Setting component versions...", bold=True)
    for cn, c in versions.items():
        _set_component_version(cfg, cn, c['version'])

def fetch_jsonnet_libs(cfg, libs):
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
    os.makedirs('dependencies/libs', exist_ok=True)
    os.makedirs('dependencies/lib', exist_ok=True)
    for lib in libs:
        libname = lib['name']
        filestext = ' '.join([ f['targetfile'] for f in lib['files'] ])
        click.echo(f" > {libname}: {filestext}")
        repo = git.clone_repository(lib['repository'], f"dependencies/libs/{libname}")
        for file in lib['files']:
            _relsymlink(repo.working_tree_dir, file['libfile'],
                    "dependencies/lib", destname=file['targetfile'])
