from pathlib import Path as P
from typing import Iterable

import click

from . import git
from .helpers import rm_tree_contents, lieutenant_query
from .cluster import Cluster
from .config import Config


def fetch_customer_catalog(config: Config, cluster: Cluster):
    click.secho("Updating cluster catalog...", bold=True)
    repo_url = cluster.catalog_repo_url
    if config.debug:
        click.echo(f" > Cloning cluster catalog {repo_url}")
    return git.clone_repository(repo_url, config.catalog_dir, config)


def _pretty_print_component_commit(name, component):
    repo = component.repo
    sha = repo.head.commit.hexsha
    short_sha = repo.git.rev_parse(sha, short=6)
    return f" * {name}: {component.version} ({short_sha})"


def _pretty_print_config_commit(name, repo):
    sha = repo.head.commit.hexsha
    short_sha = repo.git.rev_parse(sha, short=6)
    return f" * {name}: {short_sha}"


def _render_catalog_commit_msg(cfg):
    # pylint: disable=import-outside-toplevel
    import datetime

    now = datetime.datetime.now().isoformat(timespec="milliseconds")

    component_commits = [
        _pretty_print_component_commit(cn, c) for cn, c in cfg.get_components().items()
    ]
    component_commits = "\n".join(component_commits)

    config_commits = [
        _pretty_print_config_commit(c, r) for c, r in cfg.get_configs().items()
    ]
    config_commits = "\n".join(config_commits)

    return f"""Automated catalog update from Commodore

Component commits:
{component_commits}

Configuration commits:
{config_commits}

Compilation timestamp: {now}
"""


def clean_catalog(repo):
    catalogdir = P(repo.working_tree_dir, "manifests")
    click.secho("Cleaning catalog repository...", bold=True)
    # delete everything in catalog
    if catalogdir.is_dir():
        rm_tree_contents(catalogdir)
    else:
        click.echo(" > Converting old-style catalog")
        rm_tree_contents(repo.working_tree_dir)


def update_catalog(cfg: Config, targets: Iterable[str], repo):
    click.secho("Updating catalog repository...", bold=True)
    # pylint: disable=import-outside-toplevel
    from distutils import dir_util
    import textwrap

    catalogdir = P(repo.working_tree_dir, "manifests")
    for target_name in targets:
        dir_util.copy_tree(str(cfg.inventory.output_dir / target_name), str(catalogdir))

    difftext, changed = git.stage_all(repo)
    if changed:
        indented = textwrap.indent(difftext, "     ")
        message = f" > Changes:\n{indented}"
    else:
        message = " > No changes."
    click.echo(message)

    commit_message = _render_catalog_commit_msg(cfg)
    if cfg.debug:
        click.echo(" > Commit message will be")
        click.echo(textwrap.indent(commit_message, "   "))
    if changed:
        if not cfg.local:
            if cfg.interactive and cfg.push:
                cfg.push = click.confirm(" > Should the push be done?")

            if cfg.push:
                click.echo(" > Commiting changes...")
                git.commit(repo, commit_message, cfg)
                click.echo(" > Pushing catalog to remote...")
                repo.remotes.origin.push()
            else:
                click.echo(" > Skipping commit+push to catalog...")
                click.echo(" > Use flag --push to commit and push the catalog repo")
                click.echo(
                    " > Add flag --interactive to show the diff and decide on the push"
                )
        else:
            repo.head.reset(working_tree=False)
            click.echo(" > Skipping commit+push to catalog in local mode...")
    else:
        click.echo(" > Skipping commit+push to catalog...")


def catalog_list(cfg):
    clusters = lieutenant_query(cfg.api_url, cfg.api_token, "clusters", "")
    for cluster in clusters:
        display_name = cluster["displayName"]
        catalog_id = cluster["id"]
        if cfg.verbose:
            click.secho(catalog_id, nl=False, bold=True)
            click.echo(f" - {display_name}")
        else:
            click.echo(catalog_id)
