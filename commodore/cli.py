import json
import sys
from pathlib import Path
from typing import Iterable, Optional, Tuple

import click
import yaml

from dotenv import load_dotenv, find_dotenv
from commodore import __git_version__, __version__
from .catalog import catalog_list
from .config import Config, Migration
from .helpers import clean_working_tree
from .compile import compile as _compile
from .component.template import ComponentTemplater
from .component.compile import compile_component
from .inventory.render import extract_components
from .inventory.parameters import InventoryFacts
from .inventory.lint_components import lint_components
from .login import login

pass_config = click.make_pass_decorator(Config)

verbosity = click.option(
    "-v",
    "--verbose",
    count=True,
    help="Control verbosity. Can be repeated for more verbose output.",
)


def _version():
    if f"v{__version__}" != __git_version__:
        return f"{__version__} (Git version: {__git_version__})"
    return __version__


@click.group()
@click.version_option(_version(), prog_name="commodore")
@verbosity
@click.option(
    "-d",
    "--working-dir",
    default="./",
    show_default=True,
    type=click.Path(file_okay=False, dir_okay=True),
    envvar="COMMODORE_WORKING_DIR",
    help=(
        "The directory in which Commodore will fetch dependencies, "
        "inventory and catalog, and store intermediate outputs"
    ),
)
@click.pass_context
def commodore(ctx, working_dir, verbose):
    ctx.obj = Config(Path(working_dir), verbose=verbose)


@commodore.group(short_help="Interact with a cluster catalog.")
@verbosity
@pass_config
def catalog(config: Config, verbose):
    config.update_verbosity(verbose)


@catalog.command(short_help="Delete generated files.")
@verbosity
@pass_config
def clean(config: Config, verbose):
    config.update_verbosity(verbose)
    clean_working_tree(config)


api_url_option = click.option(
    "--api-url", envvar="COMMODORE_API_URL", help="Lieutenant API URL.", metavar="URL"
)
oidc_discovery_url_option = click.option(
    "--oidc-discovery-url",
    envvar="COMMODORE_OIDC_DISCOVERY_URL",
    help="The discovery URL of the IdP.",
    metavar="URL",
)
oidc_client_option = click.option(
    "--oidc-client",
    envvar="COMMODORE_OIDC_CLIENT",
    help="The OIDC client name.",
    metavar="TEXT",
)


@catalog.command(name="compile", short_help="Compile the catalog.")
@click.argument("cluster")
@api_url_option
@click.option(
    "--api-token",
    envvar="COMMODORE_API_TOKEN",
    help="Lieutenant API token.",
    metavar="TOKEN",
)
@oidc_discovery_url_option
@oidc_client_option
@click.option(
    "--local",
    is_flag=True,
    default=False,
    help=(
        "Run in local mode, local mode does not try to connect to "
        + "the Lieutenant API or fetch/push Git repositories."
    ),
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
    help="Whether to fetch Jsonnet and Kapitan dependencies in local mode. By default dependencies are fetched.",
)
@click.option(
    "-m",
    "--migration",
    help=(
        "Specify a migration that you expect to happen for the cluster catalog. "
        + "Currently Commodore only knows the Kapitan 0.29 to 0.30 migration. "
        + "When the Kapitan 0.29 to 0.30 migration is selected, Commodore will suppress "
        + "noise (changing managed-by labels, and reordered objects) caused by the "
        + "migration in the diff output."
    ),
    type=click.Choice([m.value for m in Migration], case_sensitive=False),
)
@verbosity
@pass_config
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
    if config.push and (
        config.global_repo_revision_override or config.tenant_repo_revision_override
    ):
        raise click.ClickException(
            "Cannot push changes when local global or tenant repo override is specified"
        )

    if not local:
        if not fetch_dependencies:
            click.echo(
                "--no-fetch-dependencies doesn't take effect unless --local is specified"
            )
        # Ensure we always fetch dependencies in regular mode
        fetch_dependencies = True
    config.fetch_dependencies = fetch_dependencies

    if config.api_token is None and not local:
        try:
            login(config)
        except click.ClickException:
            pass

    _compile(config, cluster)


@catalog.command(name="list", short_help="List available catalog cluster IDs")
@api_url_option
@click.option(
    "--api-token",
    envvar="COMMODORE_API_TOKEN",
    help="Lieutenant API token.",
    metavar="TOKEN",
)
@oidc_client_option
@oidc_discovery_url_option
@verbosity
@pass_config
# pylint: disable=too-many-arguments
def clusters_list_command(
    config: Config, api_url, api_token, oidc_client, oidc_discovery_url, verbose
):
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

    catalog_list(config)


@commodore.group(short_help="Interact with components.")
@verbosity
@pass_config
def component(config: Config, verbose):
    config.update_verbosity(verbose)


@component.command(name="new", short_help="Bootstrap a new component.")
@click.argument("slug")
@click.option(
    "--name",
    help="The component's name as it will be written in the documentation. Defaults to the slug.",
)
@click.option(
    "--lib/--no-lib",
    default=False,
    show_default=True,
    help="Add a component library template.",
)
@click.option(
    "--pp/--no-pp",
    default=False,
    show_default=True,
    help="Add a component postprocessing template.",
)
@click.option(
    "--owner",
    default="projectsyn",
    show_default=True,
    help="The GitHub user or project name where the component will be hosted.",
)
@click.option(
    "--copyright",
    "copyright_holder",
    default="VSHN AG <info@vshn.ch>",
    show_default=True,
    help="The copyright holder added to the license file.",
)
@click.option(
    "--golden-tests/--no-golden-tests",
    default=True,
    show_default=True,
    help="Add golden tests to the component.",
)
@click.option(
    "--matrix-tests/--no-matrix-tests",
    default=True,
    show_default=True,
    help="Enable test matrix for compile/golden tests.",
)
@verbosity
@pass_config
# pylint: disable=too-many-arguments
def component_new(
    config: Config,
    slug,
    name,
    lib,
    pp,
    owner,
    copyright_holder,
    golden_tests,
    matrix_tests,
    verbose,
):
    config.update_verbosity(verbose)
    f = ComponentTemplater(config, slug)
    f.name = name
    f.library = lib
    f.post_process = pp
    f.github_owner = owner
    f.copyright_holder = copyright_holder
    f.golden_tests = golden_tests
    f.matrix_tests = matrix_tests
    f.create()


@component.command(name="delete", short_help="Remove component from inventory.")
@click.argument("slug")
@click.option(
    "--force/--no-force",
    default=False,
    show_default=True,
    help="Don't prompt for user confirmation when deleting.",
)
@verbosity
@pass_config
# pylint: disable=too-many-arguments
def component_delete(config: Config, slug, force, verbose):
    config.update_verbosity(verbose)
    config.force = force
    f = ComponentTemplater(config, slug)
    f.delete()


@component.command(name="compile", short_help="Compile a single component.")
@click.argument("path", type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option(
    "-f",
    "--values",
    multiple=True,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    help="Specify inventory class in a YAML file (can specify multiple).",
)
@click.option(
    "-a",
    "--alias",
    metavar="ALIAS",
    help="Provide component alias to use when compiling component.",
)
@click.option(
    "-J",
    "--search-paths",
    multiple=True,
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    help="Specify additional search paths.",
)
@click.option(
    "-o",
    "--output",
    default="./",
    show_default=True,
    type=click.Path(file_okay=False, dir_okay=True),
    help="Specify output path for compiled component.",
)
@verbosity
@pass_config
# pylint: disable=too-many-arguments
def component_compile(
    config: Config, path, values, alias, search_paths, output, verbose
):
    config.update_verbosity(verbose)
    compile_component(config, path, alias, values, search_paths, output)


@commodore.group(short_help="Interact with a Commodore inventory")
@verbosity
@pass_config
def inventory(config: Config, verbose):
    config.update_verbosity(verbose)


@inventory.command(
    name="components",
    short_help="Extract component URLs and versions from the inventory",
)
@click.option(
    "-o",
    "--output-format",
    help="Output format",
    type=click.Choice(["json", "yaml"]),
    default="yaml",
)
@click.option(
    "-f",
    "--values",
    help=(
        "Extra values file to use when rendering inventory. "
        + "Used as additional reclass class. "
        + "Use a values file to specify any cluster facts. "
        + "Can be repeated."
    ),
    multiple=True,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
)
@click.option(
    " / -A",
    "--allow-missing-classes/--no-allow-missing-classes",
    default=True,
    help="Whether to allow missing classes when rendering the inventory. Defaults to true.",
)
@click.argument("global-config")
@click.argument("tenant-config", required=False)
@verbosity
@pass_config
# pylint: disable=too-many-arguments
def component_versions(
    config: Config,
    verbose,
    global_config: str,
    tenant_config: Optional[str],
    output_format: str,
    values: Iterable[str],
    allow_missing_classes: bool,
):
    config.update_verbosity(verbose)
    extra_values = [Path(v) for v in values]
    try:
        components = extract_components(
            config,
            InventoryFacts(
                global_config, tenant_config, extra_values, allow_missing_classes
            ),
        )
    except ValueError as e:
        raise click.ClickException(f"While extracting components: {e}") from e

    if output_format == "json":
        click.echo(json.dumps(components))
    else:
        click.echo(yaml.safe_dump(components))


@inventory.command(
    name="lint",
    short_help="Lint YAML files for Commodore inventory structures in the provided paths",
    no_args_is_help=True,
)
@click.argument(
    "target", type=click.Path(file_okay=True, dir_okay=True, exists=True), nargs=-1
)
@verbosity
@pass_config
def inventory_lint(config: Config, verbose: int, target: Tuple[str]):
    """Lint YAML files in the provided paths.

    The command assumes that any YAML file found in the provided paths is part of a
    Commodore inventory structure."""
    config.update_verbosity(verbose)

    if len(target) == 0:
        click.secho("> No files provided, exiting...", fg="yellow")
        sys.exit(2)

    error_counts = []
    for t in target:
        lint_target = Path(t)
        error_counts.append(lint_components(config, lint_target))

    errors = sum(error_counts)
    exit_status = 0 if errors == 0 else 1
    if errors == 0:
        click.secho("No errors 🎉 ✨", bold=True)
    if errors > 0:
        click.secho(f"Found {errors} errors", bold=True)

    sys.exit(exit_status)


@commodore.command(
    name="login",
    short_help="Login to Lieutenant",
)
@click.option(
    "--oidc-discovery-url",
    envvar="COMMODORE_OIDC_DISCOVERY_URL",
    help="The discovery URL of the IdP.",
    metavar="URL",
)
@click.option(
    "--oidc-client",
    envvar="COMMODORE_OIDC_CLIENT",
    help="The OIDC client name.",
    metavar="TEXT",
)
@api_url_option
@oidc_discovery_url_option
@oidc_client_option
@pass_config
def commodore_login(
    config: Config, oidc_discovery_url: str, oidc_client: str, api_url: str
):
    """Login to Lieutenant"""
    config.oidc_client = oidc_client
    config.oidc_discovery_url = oidc_discovery_url
    config.api_url = api_url

    login(config)


def main():
    load_dotenv(dotenv_path=find_dotenv(usecwd=True))
    commodore.main(prog_name="commodore", auto_envvar_prefix="COMMODORE")
