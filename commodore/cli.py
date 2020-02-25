import click

from .config import Config
from .helpers import clean as _clean
from .compile import compile as _compile
from .component_template import ComponentFactory

from . import __version__

pass_config = click.make_pass_decorator(Config)

verbosity = click.option('-v', '--verbose', count=True,
                         help='Control verbosity. Can be repeated for more verbose output')


@click.group()
@click.option('--api-url', metavar='URL', help='Lieutenant API URL')
@click.option('--api-token', metavar='TOKEN', help='Lieutenant API token')
@click.option('--global-git-base', metavar='URL',
              help='Base directory for global Git config repositories')
@verbosity
@click.version_option(__version__, prog_name='commodore')
@click.pass_context
# pylint: disable=too-many-arguments
def commodore(ctx, api_url, api_token, global_git_base, verbose):
    ctx.obj = Config(api_url, api_token, global_git_base, verbose)


@commodore.command(short_help='Delete generated files')
@verbosity
@pass_config
def clean(config, verbose):
    config.update_verbosity(verbose)
    _clean(config)


@commodore.command(short_help='Compile inventory and catalog')
@click.argument('cluster')
@click.option('--local', is_flag=True, default=False,
              help=('Run in local mode, Local mode does not try to connect to ' +
                    'Lieutenant API or fetch/push Git repositories.'))
@click.option('--push', is_flag=True, default=False,
              help='Push catalog to remote repository. Defaults to False')
@verbosity
@pass_config
# pylint: disable=redefined-builtin
def compile(config, cluster, local, push, verbose):
    config.update_verbosity(verbose)
    config.local = local
    config.push = push
    _compile(config, cluster)


@commodore.command(short_help='Bootstrap new component')
@click.argument('name')
@click.option('--lib/--no-lib', default=False, show_default=True,
              help='Add component library template')
@click.option('--pp/--no-pp', default=False, show_default=True,
              help='Add component postprocessing template')
@click.option('--owner', default="projectsyn", show_default=True,
              help='The GitHub user or project name where the component will be hosted')
@click.option('--copyright', 'copyright_holder',
              default="VSHN AG <info@vshn.ch>", show_default=True,
              help='The copyright holder added to the license file')
@verbosity
@pass_config
# pylint: disable=too-many-arguments
def new_component(config, name, verbose, lib, pp, owner, copyright_holder):
    config.update_verbosity(verbose)
    f = ComponentFactory(config, name)
    f.library = lib
    f.post_process = pp
    f.github_owner = owner
    f.copyright_holder = copyright_holder
    f.create()


def main():
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ModuleNotFoundError as e:
        pass

    commodore.main(prog_name='commodore', auto_envvar_prefix='COMMODORE')
