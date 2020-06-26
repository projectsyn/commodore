import click

from dotenv import load_dotenv
from importlib_metadata import version
from commodore import __git_version__
from .config import Config
from .helpers import clean_working_tree
from .compile import compile as _compile
from .component.template import ComponentFactory
from .component.compile import compile_component

pass_config = click.make_pass_decorator(Config)


def _version():
    pyversion = version('commodore')
    if f"v{pyversion}" != __git_version__:
        return f"{pyversion} (Git version: {__git_version__})"
    return pyversion


@click.group()
@click.version_option(_version(), prog_name='commodore')
@click.option('-v', '--verbose', count=True,
              help='Control verbosity. Can be repeated for more verbose output.')
@click.pass_context
def commodore(ctx, verbose):
    ctx.obj = Config(verbose=verbose)


@commodore.group(short_help='Interact with a cluster catalog.')
def catalog():
    return


@catalog.command(short_help='Delete generated files.')
@pass_config
def clean(config, verbose):
    config.update_verbosity(verbose)
    clean_working_tree(config)


@catalog.command(name='compile', short_help='Compile the catalog.')
@click.argument('cluster')
@click.option('--api-url', metavar='URL', help='Lieutenant API URL.')
@click.option('--api-token', metavar='TOKEN', help='Lieutenant API token.')
@click.option('--global-git-base', metavar='URL',
              help='Base directory for global Git config repositories.')
@click.option('--local', is_flag=True, default=False,
              help=('Run in local mode, local mode does not try to connect to ' +
                    'the Lieutenant API or fetch/push Git repositories.'))
@click.option('--push', is_flag=True, default=False,
              help='Push catalog to remote repository.')
@pass_config
# pylint: disable=too-many-arguments
def compile_catalog(config: Config, cluster, api_url, api_token, global_git_base, local, push):
    config.api_url = api_url
    config.api_token = api_token
    config.global_git_base = global_git_base
    config.local = local
    config.push = push
    _compile(config, cluster)


@commodore.group(short_help='Interact with components.')
def component():
    return


@component.command(short_help='Bootstrap a new component.')
@click.argument('name')
@click.option('--lib/--no-lib', default=False, show_default=True,
              help='Add a component library template.')
@click.option('--pp/--no-pp', default=False, show_default=True,
              help='Add a component postprocessing template.')
@click.option('--owner', default="projectsyn", show_default=True,
              help='The GitHub user or project name where the component will be hosted.')
@click.option('--copyright', 'copyright_holder',
              default="VSHN AG <info@vshn.ch>", show_default=True,
              help='The copyright holder added to the license file.')
@pass_config
# pylint: disable=too-many-arguments
def new(config: Config, name, lib, pp, owner, copyright_holder):
    f = ComponentFactory(config, name)
    f.library = lib
    f.post_process = pp
    f.github_owner = owner
    f.copyright_holder = copyright_holder
    f.create()


@component.command(name='compile', short_help='Compile a single component')
@click.argument('path', type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option('-f', '--values', multiple=True,
              type=click.Path(exists=True, file_okay=True, dir_okay=False),
              help='Specify inventory class in a YAML file (can specify multiple).')
@click.option('-J', '--search-paths', multiple=True,
              type=click.Path(exists=True, file_okay=False, dir_okay=True),
              help='Specify additional search paths.')
@click.option('-o', '--output',
              default='./', show_default=True,
              type=click.Path(exists=True, file_okay=False, dir_okay=True),
              help='Specify output path for compiled component.')
@pass_config
def compile_comp(config: Config, path, values, search_paths, output):
    compile_component(config, path, values, search_paths, output)


def main():
    load_dotenv()
    commodore.main(prog_name='commodore', auto_envvar_prefix='COMMODORE')
