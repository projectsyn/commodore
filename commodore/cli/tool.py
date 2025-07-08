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
    help="A custom version to install for the requested tool (by default the latest version is installed)",
)
@click.argument("tool")
def tool_install(
    config: Config, verbose: int, tool: str, version: Optional[str], github_token: str
):
    config.update_verbosity(verbose)
    config.github_token = github_token
    tools.install_tool(config, tool, version)


@tool_group.command(name="upgrade", short_help="Upgrade external tools")
@options.verbosity
@options.github_token
@options.pass_config
@click.option(
    "--version",
    default=None,
    metavar="VERSION",
    help="A custom version to install for the requested tool (by default the latest version is installed)",
)
@click.argument("tool")
def tool_upgrade(
    config: Config, verbose: int, tool: str, version: Optional[str], github_token: str
):
    config.update_verbosity(verbose)
    config.github_token = github_token
    tools.upgrade_tool(config, tool, version)
