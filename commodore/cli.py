import click

from .config import Config
from .helpers import clean as _clean
from .compile import compile as _compile
from .component_template import create_component

pass_config = click.make_pass_decorator(Config)

verbosity = click.option('-v', '--verbose', count=True,
                         help='Control verbosity. Can be repeated for more verbose output')


@click.group()
@click.option('--api-url', metavar='URL', help='SYNventory API URL')
@click.option('--global-git-base', metavar='URL',
              help='Base directory for global Git config repositories')
@click.option('--customer-git-base', metavar='URL',
              help='Base directory for customer Git config repositories')
@verbosity
@click.version_option('0.0.1', prog_name='commodore')
@click.pass_context
def commodore(ctx, api_url, global_git_base, customer_git_base, verbose):
    ctx.obj = Config(api_url, global_git_base, customer_git_base, verbose)


@commodore.command(short_help='Delete generated files')
@verbosity
@pass_config
def clean(config, verbose):
    config.update_verbosity(verbose)
    _clean(config)


@commodore.command(short_help='Compile inventory and catalog')
@click.argument('customer')
@click.argument('cluster')
@click.option('--local', is_flag=True, default=False,
              help='Run in local mode, Local mode does not try to connect to ' +
                   'SYNventory or fetch/push Git repositories.')
@click.option('--push', is_flag=True, default=False,
              help='Push catalog to remote repository. Defaults to False')
@verbosity
@pass_config
def compile(config, customer, cluster, local, push, verbose):
    config.update_verbosity(verbose)
    config.local = local
    config.push = push
    _compile(config, customer, cluster)


@commodore.command(short_help='Bootstrap new component')
@click.argument('name')
@click.option('--lib/--no-lib', default=False, show_default=True,
              help='Add component library template')
@click.option('--pp/--no-pp', default=False, show_default=True,
              help='Add component postprocessing template')
@verbosity
@pass_config
def new_component(config, name, verbose, lib, pp):
    config.update_verbosity(verbose)
    create_component(config, name, lib, pp)


def main():
    commodore.main(prog_name='commodore', auto_envvar_prefix='COMMODORE')
