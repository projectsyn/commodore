from __future__ import annotations

import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Optional

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
from .inventory.lint import LINTERS
from .login import login, fetch_token
from .package.compile import compile_package
from .package.template import PackageTemplater

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


CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


@click.group(context_settings=CONTEXT_SETTINGS)
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
    f = ComponentTemplater(config, slug, name=name)
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
    config: Config,
    path: str,
    values: Iterable[str],
    alias: Optional[str],
    search_paths: Iterable[str],
    output: str,
    verbose: int,
):
    config.update_verbosity(verbose)
    compile_component(config, path, alias, values, search_paths, output)


@commodore.group(short_help="Interact with a Commodore config package")
@verbosity
@pass_config
def package(config: Config, verbose: int):
    config.update_verbosity(verbose)


@package.command(name="new", short_help="Create a new config package from a template")
@click.argument("slug")
@click.option(
    "--name",
    help="The package's name as it will be written in the documentation. Defaults to the slug.",
)
@click.option(
    "--owner",
    default="projectsyn",
    show_default=True,
    help="The GitHub user or project name where the package will be hosted.",
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
    help="Add golden tests to the package.",
)
@click.option(
    "--template-url",
    default="https://github.com/projectsyn/commodore-config-package-template.git",
    show_default=True,
    help="The URL of the package cookiecutter template.",
)
@click.option(
    "--template-version",
    default="main",
    show_default=True,
    help="The package template version (Git tree-ish) to use.",
)
@click.option(
    "--output-dir",
    default="",
    show_default=True,
    type=click.Path(file_okay=False, dir_okay=True),
    help="The directory in which to place the new package.",
)
@click.option(
    "--additional-test-case",
    "-t",
    metavar="CASE",
    default=[],
    show_default=True,
    multiple=True,
    help="Additional test cases to generate in the new package. Can be repeated. "
    + "Test case `defaults` will always be generated.",
)
@verbosity
@pass_config
# pylint: disable=too-many-arguments
def package_new(
    config: Config,
    verbose: int,
    slug: str,
    name: Optional[str],
    owner: str,
    copyright_holder: str,
    golden_tests: bool,
    template_url: str,
    template_version: str,
    output_dir: str,
    additional_test_case: Iterable[str],
):
    """Create new config package repo from template.

    The command line options allow the caller to customize the remote repository
    location (only supports GitHub at the moment), the package's display name, whether
    to configure golden tests, and the licensing details.
    """
    config.update_verbosity(verbose)
    t = PackageTemplater(config, slug, name=name, output_dir=output_dir)
    t.github_owner = owner
    t.copyright_holder = copyright_holder
    t.golden_tests = golden_tests
    t.template_url = template_url
    t.template_version = template_version
    t.test_cases = ["defaults"] + list(additional_test_case)
    t.create()


@package.command(name="compile", short_help="Compile a config package standalone")
@click.argument("path", type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.argument(
    "test_class", type=click.Path(exists=False, file_okay=True, dir_okay=False)
)
@click.option(
    "-f",
    "--values",
    multiple=True,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    help="Specify additional inventory class in a YAML file (can specify multiple).",
)
@click.option(
    "--local",
    is_flag=True,
    default=False,
    help=(
        "Run in local mode, local mode reuses the contents of the working directory. "
        + "Local mode won't fetch missing components."
    ),
)
@click.option(
    " / -F",
    "--fetch-dependencies/--no-fetch-dependencies",
    default=True,
    help="Whether to fetch Jsonnet and Kapitan dependencies in local mode. "
    + "By default dependencies are fetched.",
)
@click.option(
    "-k / ",
    "--keep-dir/--no-keep-dir",
    default=False,
    show_default=True,
    help="Whether to keep the compilation temp directory after the compilation is done.",
)
@click.option(
    "--tmp-dir",
    default="",
    metavar="PATH",
    type=click.Path(exists=False, file_okay=False, dir_okay=True),
    help="Temp directory to use for compilation. Implies `--keep-dir`",
)
@verbosity
@pass_config
# pylint: disable=too-many-arguments
def package_compile(
    config: Config,
    verbose: int,
    path: str,
    test_class: str,
    values: Iterable[str],
    local: bool,
    fetch_dependencies: bool,
    keep_dir: bool,
    tmp_dir: str,
):
    config.update_verbosity(verbose)
    config.local = local
    config.fetch_dependencies = fetch_dependencies
    compile_package(config, path, test_class, values, tmp_dir, keep_dir)


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
@click.option(
    "-l",
    "--linter",
    help="Which linters to enable. Can be repeated.",
    type=click.Choice(
        list(LINTERS.keys()),
        case_sensitive=False,
    ),
    multiple=True,
    default=tuple(LINTERS.keys()),
)
@click.argument(
    "target", type=click.Path(file_okay=True, dir_okay=True, exists=True), nargs=-1
)
@verbosity
@pass_config
def inventory_lint(
    config: Config, verbose: int, target: tuple[str], linter: tuple[str]
):
    """Lint YAML files in the provided paths.

    The command assumes that any YAML file found in the provided paths is part of a
    Commodore inventory structure."""
    config.update_verbosity(verbose)

    error_counts = []
    for t in target:
        lint_target = Path(t)
        for lint in linter:
            error_counts.append(LINTERS[lint](config, lint_target))

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


@commodore.command(
    name="fetch-token",
    short_help="Fetch Lieutenant token",
)
@api_url_option
@oidc_discovery_url_option
@oidc_client_option
@pass_config
@verbosity
def commodore_fetch_token(
    config: Config,
    oidc_discovery_url: str,
    oidc_client: str,
    api_url: str,
    verbose: int,
):
    """Fetch Lieutenant token

    Get the token from the cache, if it's still valid, otherwise fetch a new token based
    on the provided OIDC config and Lieutenant URL.

    The command prints the token to stdout.
    """
    if api_url is None:
        raise click.ClickException(
            "Can't fetch Lieutenant token. Please provide the Lieutenant API URL."
        )

    config.api_url = api_url
    config.oidc_client = oidc_client
    config.oidc_discovery_url = oidc_discovery_url
    config.update_verbosity(verbose)

    token = fetch_token(config)
    click.echo(token)


def main():
    load_dotenv(dotenv_path=find_dotenv(usecwd=True))
    commodore.main(prog_name="commodore", auto_envvar_prefix="COMMODORE")
