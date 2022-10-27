"""Commands which expose Commodore's OIDC login support"""
import click

from commodore.config import Config
from commodore.login import fetch_token, login

import commodore.cli.options as options


@click.command(
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


@click.command(
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
