from __future__ import annotations

import multiprocessing

from pathlib import Path

import click

from dotenv import load_dotenv, find_dotenv
from commodore import __git_version__, __version__
from commodore.config import Config

import commodore.cli.options as options

from .catalog import catalog_group
from .component import component_group
from .inventory import inventory_group
from .package import package_group
from .oidc import commodore_fetch_token, commodore_login


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
commodore.add_command(inventory_group)
commodore.add_command(package_group)
commodore.add_command(commodore_login)
commodore.add_command(commodore_fetch_token)


def main():
    multiprocessing.set_start_method("spawn")

    load_dotenv(dotenv_path=find_dotenv(usecwd=True))
    commodore.main(
        prog_name="commodore", auto_envvar_prefix="COMMODORE", max_content_width=100
    )
