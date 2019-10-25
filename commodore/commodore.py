import click, json, os
from kapitan.resources import inventory_reclass

from . import git
from .dependency_mgmt import (
        fetch_components,
        fetch_jsonnet_libs,
        set_component_versions
    )
from .helpers import clean, api_request, kapitan_compile, ApiError, rm_tree_contents
from .postprocess import postprocess_components

def fetch_cluster_spec(cfg, customer, cluster):
    return api_request(cfg.api_url, 'inventory', customer, cluster)

def fetch_config(cfg, response):
    config = response['global']['config']
    click.secho(f"Updating global config...", bold=True)
    repo = git.clone_repository(f"{cfg.global_git_base}/{config}.git", f"inventory/classes/global")
    cfg.register_config('global', repo)

def fetch_target(cfg, customer, cluster):
    return api_request(cfg.api_url, 'targets', customer, cluster, is_json=False)

def update_target(cfg, customer, cluster):
    click.secho("Updating Kapitan target...", bold=True)
    try:
        target = fetch_target(cfg, customer, cluster)
    except ApiError as e:
        raise click.ClickException(f"While fetching target: {e}") from e

    os.makedirs('inventory/targets', exist_ok=True)
    with open('inventory/targets/cluster.yml', 'w') as tgt:
        tgt.write(target)

    return 'cluster'

def fetch_customer_config(cfg, repo, customer):
    if repo is None:
        repo = f"{cfg.customer_git_base}/{customer}.git"
    click.secho("Updating customer config...", bold=True)
    repo = git.clone_repository(repo, f"inventory/classes/{customer}")
    cfg.register_config('customer', repo)

def fetch_customer_catalog(cfg, target_name, repoinfo):
    click.secho("Updating customer catalog...", bold=True)
    return git.clone_repository(repoinfo['url'], 'catalog')

def _render_catalog_commit_msg(cfg):
    import datetime
    now = datetime.datetime.now().isoformat(timespec='milliseconds')

    component_commits = [ f" * {cn}: {c.repo.head.commit.hexsha}" for cn, c in cfg.get_components().items() ]
    component_commits = '\n'.join(component_commits)

    config_commits = [ f" * {c}: {r.head.commit.hexsha}" for c, r in cfg.get_configs().items() ]
    config_commits = '\n'.join(config_commits)

    return f"""
Automated catalog update from Commodore

Component commits:
{component_commits}

Configuration commits:
{config_commits}

Compilation timestamp: {now}
"""


def update_catalog(cfg, target_name, repo):
    click.secho("Updating catalog repository...", bold=True)
    from distutils import dir_util
    import textwrap
    catalogdir = repo.working_tree_dir
    # delete everything in catalog
    rm_tree_contents(catalogdir)
    # copy compiled catalog into catalog directory
    dir_util.copy_tree(f"compiled/{target_name}", catalogdir)

    difftext, changed = git.stage_all(repo)
    if changed:
        indented = textwrap.indent(difftext, '     ')
        message = f" > Changes:\n{indented}"
    else:
        message = " > No changes."
    click.echo(message)

    if changed:
        if not cfg.local:
            click.echo(" > Commiting changes...")
            message = _render_catalog_commit_msg(cfg)
            repo.index.commit(message)
            click.echo(" > Pushing catalog to remote...")
            repo.remotes.origin.push()
        else:
            repo.head.reset(working_tree=True)
            click.echo(" > Skipping commit+push to catalog in local mode...")
    else:
        click.echo(" > Skipping commit+push to catalog...")


def compile(config, customer, cluster):
    if config.local:
        click.secho("Running in local mode", bold=True)
        click.echo(" > Will use existing inventory, dependencies, and catalog")
        target_name = config.local
        if not os.path.isfile(f"inventory/targets/{target_name}.yml"):
            raise click.ClickException(f"Invalid target: {target_name}")
        click.echo(f" > Using target: {target_name}")
        click.secho("Registering components...", bold=True)
        for c in os.listdir('dependencies'):
            # Skip jsonnet libs when collecting components
            if c == "lib" or c == "libs":
                continue
            click.echo(f" > {c}")
            repo = git.init_repository(f"dependencies/{c}")
            config.register_component(c, repo)
        click.secho("Configuring catalog repo...", bold=True)
        catalog_repo = git.init_repository(f"catalog")
    else:
        clean()

        try:
            inv = fetch_cluster_spec(config, customer, cluster)
        except ApiError as e:
            raise click.ClickException(f"While fetching cluster specification: {e}") from e

        target_name = update_target(config, customer, cluster)

        # Fetch all Git repos
        try:
            fetch_config(config, inv)
            fetch_components(config, inv)
            fetch_customer_config(config, inv['cluster'].get('override', None), customer)
            fetch_jsonnet_libs(config, inv)
            catalog_repo = fetch_customer_catalog(config, target_name, inv['catalog_repo'])
        except Exception as e:
            raise click.ClickException(f"While cloning git repositories: {e}") from e

    # Compile kapitan inventory to extract component versions. Component
    # versions are assumed to be defined in the inventory key
    # 'parameters.component_versions'
    kapitan_inventory = inventory_reclass('inventory')['nodes'][target_name]
    versions = kapitan_inventory['parameters'].get('component_versions', None)
    if versions and not config.local:
        set_component_versions(config, versions)

    p = kapitan_compile()
    if p.returncode != 0:
        raise click.ClickException(f"Catalog compilation failed")

    postprocess_components(kapitan_inventory, target_name, config.get_components())

    update_catalog(config, target_name, catalog_repo)

    click.secho("Catalog compiled! 🎉", bold=True)
