"""Commands which interact with cluster catalogs"""
from __future__ import annotations

import click

from pathlib import Path

from commodore.catalog import catalog_list, Migration
from commodore.compile import compile as _compile
from commodore.config import Config, parse_dynamic_facts_from_cli
from commodore.helpers import clean_working_tree, lieutenant_query, ApiError
from commodore.login import login

import commodore.cli.options as options


@click.group(
    name="catalog",
    short_help="Interact with a cluster catalog.",
)
@options.verbosity
@options.pass_config
def catalog_group(config: Config, verbose):
    config.update_verbosity(verbose)


@catalog_group.command(short_help="Delete generated files.")
@options.verbosity
@options.pass_config
def clean(config: Config, verbose):
    config.update_verbosity(verbose)
    clean_working_tree(config)


def _complete_clusters(ctx: click.Context, _, incomplete: str) -> list[str]:
    config = Config(Path("."))
    config.api_url = ctx.params["api_url"]
    config.api_token = ctx.params["api_token"]
    config.oidc_client = ctx.params["oidc_client"]
    config.oidc_discovery_url = ctx.params["oidc_discovery_url"]

    try:
        if config.api_token is None:
            login(config)
        clusters = lieutenant_query(config.api_url, config.api_token, "clusters", "")
    except (click.ClickException, ApiError):
        # If we encounter any errors, ignore them.
        # We shouldn't print errors during completion
        return []
    return [c["id"] for c in clusters if "id" in c and c["id"].startswith(incomplete)]


@catalog_group.command(name="compile", short_help="Compile the catalog.")
@click.argument("cluster", shell_complete=_complete_clusters)
@options.api_url
@options.api_token
@options.oidc_discovery_url
@options.oidc_client
@options.local(
    "Run in local mode, local mode does not try to connect to "
    + "the Lieutenant API or fetch/push Git repositories."
)
@click.option(
    "--push", is_flag=True, default=False, help="Push catalog to remote repository."
)
@click.option(
    "-i",
    "--interactive",
    is_flag=True,
    default=False,
    help="Prompt confirmation to push to remote repository.",
)
@click.option(
    "--git-author-name",
    envvar="GIT_AUTHOR_NAME",
    metavar="USERNAME",
    help="Name of catalog commit author",
)
@click.option(
    "--git-author-email",
    envvar="GIT_AUTHOR_EMAIL",
    metavar="EMAIL",
    help="E-mail address of catalog commit author",
)
@click.option(
    "-g",
    "--global-repo-revision-override",
    envvar="GLOBAL_REPO_REVISION_OVERRIDE",
    metavar="REV",
    help=(
        "Git revision (tree-ish) to checkout for the global config repo "
        + "(overrides configuration in Lieutenant tenant & cluster)"
    ),
)
@click.option(
    "-t",
    "--tenant-repo-revision-override",
    envvar="TENANT_REPO_REVISION_OVERRIDE",
    metavar="REV",
    help=(
        "Git revision (tree-ish) to checkout for the tenant config repo "
        + "(overrides configuration in Lieutenant cluster)"
    ),
)
@click.option(
    " / -F",
    "--fetch-dependencies/--no-fetch-dependencies",
    default=True,
    help=(
        "Whether to fetch Jsonnet and Kapitan dependencies in local mode. "
        + "By default dependencies are fetched."
    ),
)
@click.option(
    "-m",
    "--migration",
    help=(
        "Specify a migration that you expect to happen for the cluster catalog. "
        + "Currently known are the Kapitan 0.29 to 0.30 migration and "
        + "a generic migration ignoring all non-functional YAML formatting changes. "
        + "When the Kapitan 0.29 to 0.30 migration is selected, Commodore will suppress "
        + "noise (changing managed-by labels, and reordered objects) caused by the "
        + "migration in the diff output. "
        + "When the ignore YAML formatting migration is selected, Commodore will suppress "
        + "noise such as reordered objects, indentation and flow changes of lists or "
        + "differences in string representation."
    ),
    type=click.Choice([m.value for m in Migration], case_sensitive=False),
)
@click.option(
    "-d",
    "--dynamic-fact",
    type=str,
    metavar="KEY=VALUE",
    multiple=True,
    help=(
        "Fallback dynamic facts to use when compiling a cluster which hasn't "
        + "reported its dynamic facts yet. Commodore will never use values provided "
        + "through this parameter if the cluster response from the API has a dynamic "
        + "facts field. Can be repeated. Commodore expects each fact to be specified "
        + "as key=value. Nested keys can be provided as `path.to.key`. Commodore will "
        + "parse values as JSON if they're prefixed by `json:`. If the same key is "
        + "provided multiple times, the last occurrence overrides the previous values. "
        + "When providing a value for a key as JSON, previously specified subkeys of "
        + "that key will be overwritten. Nested keys are ignored if any non-leaf level "
        + "of the requested key already contains a non-dictionary value. If a value "
        + "prefixed with `json:` isn't valid JSON, it will be skipped."
    ),
)
@click.option(
    "--force/--no-force",
    default=False,
    show_default=True,
    help="With `--force` local changes in tenant, global, or dependency repos are discarded. "
    + "In the global and tenant repo, untracked files, uncommitted changes in tracked files, "
    + "local commits and local branches count as local changes. In dependency repos only "
    + "uncommitted changes in tracked files count as local changes."
    + "The parameter has no effect if `--local` is given.",
)
@options.verbosity
@options.pass_config
# pylint: disable=too-many-arguments
# pylint: disable=too-many-locals
def compile_catalog(
    config: Config,
    cluster,
    api_url,
    api_token,
    oidc_client,
    oidc_discovery_url,
    local,
    push,
    interactive,
    verbose,
    git_author_name,
    git_author_email,
    global_repo_revision_override,
    tenant_repo_revision_override,
    fetch_dependencies,
    migration,
    dynamic_fact: str,
    force: bool,
):
    config.update_verbosity(verbose)
    config.api_url = api_url
    config.api_token = api_token
    config.local = local
    config.push = push
    config.interactive = interactive
    config.username = git_author_name
    config.usermail = git_author_email
    config.global_repo_revision_override = global_repo_revision_override
    config.tenant_repo_revision_override = tenant_repo_revision_override
    config.migration = migration
    config.oidc_client = oidc_client
    config.oidc_discovery_url = oidc_discovery_url
    config.fetch_dependencies = fetch_dependencies
    config.dynamic_facts = parse_dynamic_facts_from_cli(dynamic_fact)
    config.force = not config.local and force

    if config.push and (
        config.global_repo_revision_override or config.tenant_repo_revision_override
    ):
        raise click.ClickException(
            "Cannot push changes when local global or tenant repo override is specified"
        )

    if config.api_token is None and not local:
        try:
            login(config)
        except click.ClickException:
            pass

    _compile(config, cluster)


@catalog_group.command(name="list", short_help="List available catalog cluster IDs")
@options.api_url
@options.api_token
@options.oidc_client
@options.oidc_discovery_url
@click.option("-o", "--out", help="Output format. One of: (json, yaml, id)")
@click.option(
    "-t",
    "--tenant",
    help="If non-empty, only show clusters of the tenant with the provided ID",
)
@click.option(
    "--sort-by",
    help="If non-empty, sort list using this flag specification. One of: (id, tenant, displayName)",
)
@options.verbosity
@options.pass_config
# pylint: disable=too-many-arguments
def clusters_list_command(
    config: Config,
    api_url,
    api_token,
    oidc_client,
    oidc_discovery_url,
    verbose,
    out,
    tenant,
    sort_by,
):
    """This command lists all cluster catalogs registered in the provided Lieutenant API.

    By default, the command will return the list of clusters in a
    human-readable table. Other output formats are available through parameter
    `--out`.

     Additionally, the command allows listing only the catalogs for a specific
     tenant and to sort the output by cluster ID, tenant, or display name with
     the `--tenant` and `--sort-by` flags.

    """

    config.update_verbosity(verbose)
    config.api_url = api_url
    config.api_token = api_token
    config.oidc_client = oidc_client
    config.oidc_discovery_url = oidc_discovery_url

    if config.api_token is None:
        try:
            login(config)
        except click.ClickException:
            pass

    catalog_list(config, out, tenant=tenant, sort_by=sort_by)
