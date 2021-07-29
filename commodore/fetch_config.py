import click
from . import git

from .cluster import Cluster
from .config import Config


def fetch_global_config(cfg: Config, cluster: Cluster):
    click.secho("Updating global config...", bold=True)
    repo = git.clone_repository(
        cluster.global_git_repo_url, cfg.inventory.global_config_dir, cfg
    )
    rev = cluster.global_git_repo_revision
    if cfg.global_repo_revision_override:
        rev = cfg.global_repo_revision_override
    if rev:
        git.checkout_version(repo, rev)
    cfg.register_config("global", repo)


def fetch_customer_config(cfg: Config, cluster: Cluster):
    click.secho("Updating customer config...", bold=True)
    repo_url = cluster.config_repo_url
    if cfg.debug:
        click.echo(f" > Cloning customer config {repo_url}")
    repo = git.clone_repository(
        repo_url, cfg.inventory.tenant_config_dir(cluster.tenant_id), cfg
    )
    rev = cluster.config_git_repo_revision
    if cfg.tenant_repo_revision_override:
        rev = cfg.tenant_repo_revision_override
    if rev:
        git.checkout_version(repo, rev)
    cfg.register_config("customer", repo)
