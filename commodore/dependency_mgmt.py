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
    os.symlink(os.path.abspath(f"{target_directory}/class/{component}.yml"), f"inventory/classes/components/{component}.yml")
    libdir = f"{target_directory}/lib"
    if os.path.isdir(libdir):
        for file in os.listdir(libdir):
            click.echo(f"     > installing template library: {file}")
            _relsymlink(f"{target_directory}/lib", file, "dependencies/lib")

def fetch_components(cfg, response):
    components = response['global']['components']
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

def set_component_versions(cfg, versions):
    click.secho("Setting component versions...", bold=True)
    for cn, c in versions.items():
        _set_component_version(cfg, cn, c['version'])

def fetch_jsonnet_libs(cfg, response):
    click.secho("Updating Jsonnet libraries...", bold=True)
    os.makedirs('dependencies/libs', exist_ok=True)
    os.makedirs('dependencies/lib', exist_ok=True)
    libs = response['global']['jsonnet_libs']
    for lib in libs:
        libname = lib['name']
        filestext = ' '.join([ f['targetfile'] for f in lib['files'] ])
        click.echo(f" > {libname}: {filestext}")
        repo = git.clone_repository(lib['repository'], f"dependencies/libs/{libname}")
        for file in lib['files']:
            os.symlink(os.path.abspath(f"{repo.working_tree_dir}/{file['libfile']}"),
                    f"dependencies/lib/{file['targetfile']}")
