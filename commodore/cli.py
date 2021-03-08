import multiprocessing
from pathlib import Path

import click

from dotenv import load_dotenv
from importlib_metadata import version
from commodore import __git_version__
from .catalog import catalog_list
from .config import Config
from .helpers import clean_working_tree
from .compile import compile as _compile
from .component.template import ComponentTemplater
from .component.compile import compile_component

pass_config = click.make_pass_decorator(Config)

verbosity = click.option(
    "-v",
    "--verbose",
    count=True,
    help="Control verbosity. Can be repeated for more verbose output.",
)


def _version():
    pyversion = version("commodore")
    if f"v{pyversion}" != __git_version__:
        return f"{pyversion} (Git version: {__git_version__})"
    return pyversion


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


@catalog.command(name="compile", short_help="Compile the catalog.")
@click.argument("cluster")
@click.option(
    "--api-url", envvar="COMMODORE_API_URL", help="Lieutenant API URL.", metavar="URL"
)
@click.option(
    "--api-token",
    envvar="COMMODORE_API_TOKEN",
    help="Lieutenant API token.",
    metavar="TOKEN",
)
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
@verbosity
@pass_config
# pylint: disable=too-many-arguments
def compile_catalog(
    config: Config,
    cluster,
    api_url,
    api_token,
    local,
    push,
    interactive,
    verbose,
    git_author_name,
    git_author_email,
):
    config.update_verbosity(verbose)
    config.api_url = api_url
    config.api_token = api_token
    config.local = local
    config.push = push
    config.interactive = interactive
    config.username = git_author_name
    config.usermail = git_author_email
    _compile(config, cluster)


@catalog.command(name="list", short_help="List available catalog cluster IDs")
@click.option(
    "--api-url", envvar="COMMODORE_API_URL", help="Lieutenant API URL.", metavar="URL"
)
@click.option(
    "--api-token",
    envvar="COMMODORE_API_TOKEN",
    help="Lieutenant API token.",
    metavar="TOKEN",
)
@verbosity
@pass_config
def clusters_list_command(config: Config, api_url, api_token, verbose):
    config.update_verbosity(verbose)
    config.api_url = api_url
    config.api_token = api_token
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
@verbosity
@pass_config
# pylint: disable=too-many-arguments
def component_new(
    config: Config, slug, name, lib, pp, owner, copyright_holder, verbose
):
    config.update_verbosity(verbose)
    f = ComponentTemplater(config, slug)
    f.name = name
    f.library = lib
    f.post_process = pp
    f.github_owner = owner
    f.copyright_holder = copyright_holder
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
def component_compile(config: Config, path, values, search_paths, output, verbose):
    config.update_verbosity(verbose)
    compile_component(config, path, values, search_paths, output)


def main():
    # set 'fork' method as a more deterministic/conservative
    # and compatible multiprocessing method for Linux and MacOS
    multiprocessing.set_start_method("fork")
    load_dotenv()
    commodore.main(prog_name="commodore", auto_envvar_prefix="COMMODORE")
