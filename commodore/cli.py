import click, sys

from .config import Config
from .helpers import clean as _clean
from .commodore import compile as _compile

pass_config = click.make_pass_decorator(Config)

@click.group()
@click.option('--api-url', envvar='API_URL', metavar='URL',
              help='SYNventory API URL')
@click.option('--global-git-base', envvar='GLOBAL_GIT_BASE', metavar='URL',
              help='Base directory for global Git config repositories')
@click.option('--customer-git-base', envvar='CUSTOMER_GIT_BASE', metavar='URL',
              help='Base directory for customer Git config repositories')
@click.version_option('0.0.1', prog_name='commodore')
@click.pass_context
def commodore(ctx, api_url, global_git_base, customer_git_base):
    ctx.obj = Config(api_url, global_git_base, customer_git_base)

@commodore.command(short_help='Delete generated files')
@pass_config
def clean(ctx):
    _clean()

@commodore.command(short_help='Compile inventory and catalog')
@click.argument('customer')
@click.argument('cluster')
@click.option('--local', envvar='LOCAL', metavar='TARGET',
              help='Run in local mode, Local mode does not try to connect to ' + \
                   'SYNventory or fetch/push Git repositories. TARGET specifies ' + \
                   'the Kapitan target to compile')
@pass_config
def compile(config, customer, cluster, local):
    config.local = local
    _compile(config, customer, cluster)
