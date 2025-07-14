from typing import Optional

import click

import commodore.cli.options as options

from commodore import tools
from commodore.config import Config


@click.group(
    name="tool",
    short_help="Manage required external tools",
)
@options.verbosity
@options.pass_config
@options.github_token
def tool_group(config: Config, verbose: int, github_token: str):
    """Commands to manage required external tools.

    Currently, `helm`, jsonnet-bundler/`jb`, and `kustomize` are required
    external tools.
    """
    config.update_verbosity(verbose)
    config.managed_tools = tools.load_state()
    config.github_token = github_token


@tool_group.command(name="list", short_help="List external tools")
@options.verbosity
@options.pass_config
@options.github_token
@click.option(
    "--version-check/--skip-version-check",
    " / -V",
    default=True,
    help="Query GitHub API to get latest version",
)
def tool_list(config: Config, verbose: int, github_token: str, version_check: bool):
    """List the version, location and management state of the required external tools.

    Currently, `helm`, jsonnet-bundler/`jb`, and `kustomize` are required
    external tools. By default, the command also queries the GitHub API to
    determine the latest available version of each tool and indicates whether an
    update is available.

    Optionally, the command accepts a GitHub personal access token (PAT) to
    avoid running into the fairly strict unauthenticated GitHub rate limits.
    """
    config.update_verbosity(verbose)
    config.github_token = github_token
    tools.list_tools(config, version_check)


@tool_group.command(name="install", short_help="Install external tools")
@options.verbosity
@options.pass_config
@options.github_token
@click.option(
    "--version",
    default=None,
    metavar="VERSION",
    help="A version to install for the requested tool. "
    + "By default, the latest version is installed.",
)
@click.option(
    "--missing",
    is_flag=True,
    default=False,
    help="Install the latest version for all currently unmanaged tools. "
    + "This flag and providing a tool name on the command line are mutually exclusive.",
)
@click.argument("tool", required=False, default="")
def tool_install(
    config: Config,
    verbose: int,
    tool: str,
    version: Optional[str],
    github_token: str,
    missing: bool,
):
    """Install one of the required tools in `$XDG_CACHE_DIR/commodore/tools`.

    The command will fail for tools which are already managed by Commodore.

    By default, the command will install the latest available tool version. For
    `helm` and `kustomize`, the command downloads the official installation
    scripts and executes them with appropriate arguments. For `jb`, the command
    directly downloads the requested version from the GitHub release page.

    Optionally, the command accepts a tool version to install. The command
    accepts versions prefixed  with "v" and unprefixed versions.

    Alternatively, the command can install the latest version for all required
    tools which aren't managed by Commodore yet by passing flag `--missing`.
    This flag is mutually exclusive with providing a tool name.
    """
    config.update_verbosity(verbose)
    config.github_token = github_token

    if not tool and not missing or tool and missing:
        raise click.ClickException(
            "`commodore tool install` expects to be called with either a tool name or the `--missing` flag."
        )
    if missing and version:
        click.secho(
            "Flag `--version` has no effect when calling the command with `--missing`.",
            fg="yellow",
        )

    if missing:
        tools.install_missing_tools(config)
    else:
        tools.install_tool(config, tool, version)


@tool_group.command(name="upgrade", short_help="Upgrade external tools")
@options.verbosity
@options.github_token
@options.pass_config
@click.option(
    "--version",
    default=None,
    metavar="VERSION",
    help="A version to upgrade (or downgrade) to for the requested tool. "
    + "By default, the tool is upgraded to the latest version.",
)
@click.option(
    "--all",
    is_flag=True,
    default=False,
    help="Upgrade all currently managed tools to their latest versions. "
    + "This flag and providing a tool name on the command line are mutually exclusive.",
)
@click.argument("tool", required=False, default="")
def tool_upgrade(
    config: Config,
    verbose: int,
    tool: str,
    version: Optional[str],
    github_token: str,
    all: bool,
):
    """Upgrade (or downgrade) one of the required tools in `$XDG_CACHE_DIR/commodore/tools`.

    The command will fail for tools which aren't managed by Commodore yet.

    By default, the command will upgrade the tool to the latest available
    version. For `helm` and `kustomize`, the command downloads the official
    installation scripts and executes them with appropriate arguments. For `jb`,
    the command directly downloads the requested version from the GitHub release
    page.

    Optionally, the command accepts a tool version to upgrade (or downgrade) to.
    The command accepts versions prefixed with "v" and unprefixed versions.

    Alternatively, the command can upgrade all managed tools to their latest
    versions by passing flag `--all`. This flag is mutually exclusive with
    providing a tool name.
    """
    config.update_verbosity(verbose)
    config.github_token = github_token

    if not tool and not all or tool and all:
        raise click.ClickException(
            "`commodore tool upgrade` expects to be called with either a tool name or the `--all` flag."
        )
    if all and version:
        click.secho(
            "Flag `--version` has no effect when calling the command with `--all`.",
            fg="yellow",
        )
    if all:
        tools.upgrade_all_tools(config)
    else:
        tools.upgrade_tool(config, tool, version)
