import click

from . import git
from .helpers import rm_tree_contents

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
