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
@click.version_option('0.0.1')
@click.pass_context
def main(ctx, api_url, global_git_base, customer_git_base):
    ctx.obj = Config(api_url, global_git_base, customer_git_base)

@main.command(short_help='Delete generated files')
@pass_config
def clean(ctx):
    _clean()

@main.command(short_help='Compile inventory and catalog')
@click.argument('customer')
@click.argument('cluster')
@pass_config
def compile(config, customer, cluster):
    _compile(config, customer, cluster)

if __name__ == "__main__":
    main()
