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
from commodore.config import Config
from commodore.inventory.render import (
    extract_components,
    extract_packages,
    extract_parameters,
)
from commodore.inventory.parameters import InventoryFacts
from commodore.inventory.lint import LINTERS
from commodore.login import login, fetch_token

import commodore.cli.options as options

from .catalog import catalog_group
from .component import component_group
from .package import package_group


def _version():
    if f"v{__version__}" != __git_version__:
        return f"{__version__} (Git version: {__git_version__})"
    return __version__


CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


@click.group(context_settings=CONTEXT_SETTINGS)
@click.version_option(_version(), prog_name="commodore")
@options.verbosity
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


commodore.add_command(catalog_group)
commodore.add_command(component_group)
commodore.add_command(package_group)


@commodore.group(short_help="Interact with a Commodore inventory")
@options.verbosity
@options.pass_config
def inventory(config: Config, verbose):
    config.update_verbosity(verbose)


@inventory.command(
    name="show",
    short_help="Returns the rendered inventory",
)
@options.inventory_output_format
@options.inventory_values
@options.inventory_allow_missing_classes
@click.argument("global-config")
@click.argument("tenant-config", required=False)
@options.verbosity
@options.pass_config
# pylint: disable=too-many-arguments
def inventory_show(
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
        inv = extract_parameters(
            config,
            InventoryFacts(
                global_config,
                tenant_config,
                extra_values,
                allow_missing_classes,
                ignore_class_notfound_warning=False,
            ),
        )
    except ValueError as e:
        raise click.ClickException(f"While rendering inventory: {e}") from e

    if output_format == "json":
        click.echo(json.dumps(inv))
    else:
        click.echo(yaml.safe_dump(inv))


@inventory.command(
    name="components",
    short_help="Extract component URLs and versions from the inventory",
)
@options.inventory_output_format
@options.inventory_values
@options.inventory_allow_missing_classes
@click.argument("global-config")
@click.argument("tenant-config", required=False)
@options.verbosity
@options.pass_config
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
                global_config,
                tenant_config,
                extra_values,
                allow_missing_classes,
                ignore_class_notfound_warning=False,
            ),
        )
    except ValueError as e:
        raise click.ClickException(f"While extracting components: {e}") from e

    if output_format == "json":
        click.echo(json.dumps(components))
    else:
        click.echo(yaml.safe_dump(components))


@inventory.command(
    name="packages",
    short_help="Extract package URLs and versions from the inventory",
)
@options.inventory_output_format
@options.inventory_values
@options.inventory_allow_missing_classes
@click.argument("global-config")
@click.argument("tenant-config", required=False)
@options.verbosity
@options.pass_config
# pylint: disable=too-many-arguments
def package_versions(
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
        pkgs = extract_packages(
            config,
            InventoryFacts(
                global_config,
                tenant_config,
                extra_values,
                allow_missing_classes,
                ignore_class_notfound_warning=False,
            ),
        )
    except ValueError as e:
        raise click.ClickException(f"While extracting packages: {e}") from e

    if output_format == "json":
        click.echo(json.dumps(pkgs))
    else:
        click.echo(yaml.safe_dump(pkgs))


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
@click.option(
    "--ignore-patterns",
    help="Glob pattern(s) indicating path(s) to ignore",
    type=click.STRING,
    multiple=True,
    default=(),
)
@click.argument(
    "target", type=click.Path(file_okay=True, dir_okay=True, exists=True), nargs=-1
)
@options.verbosity
@options.pass_config
def inventory_lint(
    config: Config,
    verbose: int,
    target: tuple[str, ...],
    linter: tuple[str, ...],
    ignore_patterns: tuple[str, ...],
):
    """Lint YAML files in the provided paths.

    The command assumes that any YAML file found in the provided paths is part of a
    Commodore inventory structure.

    Individual files or whole directory trees can be ignored by providing glob patterns.
    Glob patterns can be provided in command line argument `--ignore-patterns` or in
    `.commodoreignore` in the provided path. Patterns provided in `--ignore-patterns`
    are applied in each target path. In contrast, `.commodoreignore` files are only
    applied to the target path in which they're saved.

    The provided patterns are expanded recursively using Python's `glob` library. You
    can use `*`, `?`, and character ranges expressed as `[]` with the usual semantics of
    shell globbing. Additionally, you can use `**` to indicate an arbitrary amount of
    subdirectories. Patterns which start with `/` are treated as anchored in the target
    path. All other patterns are treated as matching any subpath in the target path."""
    config.update_verbosity(verbose)

    error_counts = []
    for t in target:
        lint_target = Path(t)
        for lint in linter:
            error_counts.append(LINTERS[lint](config, lint_target, ignore_patterns))

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
@options.api_url
@options.oidc_discovery_url
@options.oidc_client
@options.pass_config
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
@options.api_url
@options.oidc_discovery_url
@options.oidc_client
@options.pass_config
@options.verbosity
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
    commodore.main(
        prog_name="commodore", auto_envvar_prefix="COMMODORE", max_content_width=100
    )
