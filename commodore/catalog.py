import click
from pathlib import Path as P

from . import git
from .helpers import rm_tree_contents

def fetch_customer_catalog(cfg, target_name, repoinfo):
    click.secho('Updating customer catalog...', bold=True)
    return git.clone_repository(repoinfo['url'], 'catalog')

def _pretty_print_component_commit(name, component):
    repo = component.repo
    sha = repo.head.commit.hexsha
    short_sha = repo.git.rev_parse(sha, short=6)
    return f" * {name}:{component.version} ({short_sha})"

def _pretty_print_config_commit(name, repo):
    sha = repo.head.commit.hexsha
    short_sha = repo.git.rev_parse(sha, short=6)
    return f" * {name}: {short_sha}"

def _render_catalog_commit_msg(cfg):
    import datetime
    now = datetime.datetime.now().isoformat(timespec='milliseconds')

    component_commits = [ _pretty_print_component_commit(cn, c) for cn, c in cfg.get_components().items() ]
    component_commits = '\n'.join(component_commits)

    config_commits = [ _pretty_print_config_commit(c, r) for c, r in cfg.get_configs().items() ]
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
    click.secho('Updating catalog repository...', bold=True)
    from distutils import dir_util
    import textwrap
    catalogdir = repo.working_tree_dir
    # delete everything in catalog
    rm_tree_contents(catalogdir)
    # copy compiled catalog into catalog directory
    dir_util.copy_tree(P('compiled') / target_name, catalogdir)

    difftext, changed = git.stage_all(repo)
    if changed:
        indented = textwrap.indent(difftext, '     ')
        message = f" > Changes:\n{indented}"
    else:
        message = ' > No changes.'
    click.echo(message)

    commit_message = _render_catalog_commit_msg(cfg)
    if cfg.debug:
        click.echo(' > Commit message will be')
        click.echo(textwrap.indent(commit_message, '   '))
    if changed:
        if not cfg.local:
            if cfg.push:
                click.echo(' > Commiting changes...')
                git.commit(repo, commit_message)
                click.echo(' > Pushing catalog to remote...')
                repo.remotes.origin.push()
            else:
                click.echo(' > Skipping commit+push to catalog...')
                click.echo(' > Use flag --push to commit and push the catalog repo')
        else:
            repo.head.reset(working_tree=False)
            click.echo(' > Skipping commit+push to catalog in local mode...')
    else:
        click.echo(' > Skipping commit+push to catalog...')
