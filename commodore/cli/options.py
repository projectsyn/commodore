"""Click options which are reused for multiple commands"""
import click

from commodore.config import Config

pass_config = click.make_pass_decorator(Config)

verbosity = click.option(
    "-v",
    "--verbose",
    count=True,
    help="Control verbosity. Can be repeated for more verbose output.",
)

inventory_output_format = click.option(
    "-o",
    "--output-format",
    help="Output format",
    type=click.Choice(["json", "yaml"]),
    default="yaml",
)

inventory_values = click.option(
    "-f",
    "--values",
    help=(
        "Extra values file to use when rendering inventory. "
        + "Used as additional reclass class. "
        + "Use a values file to specify any cluster facts. "
        + "Can be repeated."
    ),
    multiple=True,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
)

inventory_allow_missing_classes = click.option(
    " / -A",
    "--allow-missing-classes/--no-allow-missing-classes",
    default=True,
    help="Whether to allow missing classes when rendering the inventory. Defaults to true.",
)

api_url = click.option(
    "--api-url", envvar="COMMODORE_API_URL", help="Lieutenant API URL.", metavar="URL"
)

api_token = click.option(
    "--api-token",
    envvar="COMMODORE_API_TOKEN",
    help="Lieutenant API token.",
    metavar="TOKEN",
)

oidc_discovery_url = click.option(
    "--oidc-discovery-url",
    envvar="COMMODORE_OIDC_DISCOVERY_URL",
    help="The discovery URL of the IdP.",
    metavar="URL",
)

oidc_client = click.option(
    "--oidc-client",
    envvar="COMMODORE_OIDC_CLIENT",
    help="The OIDC client name.",
    metavar="TEXT",
)

github_token = click.option(
    "--github-token",
    help="GitHub API token",
    envvar="COMMODORE_GITHUB_TOKEN",
    default="",
)

pr_branch = click.option(
    "--pr-branch",
    "-b",
    metavar="BRANCH",
    default="template-sync",
    show_default=True,
    type=str,
    help="Branch name to use for updates from template",
)

pr_label = click.option(
    "--pr-label",
    "-l",
    metavar="LABEL",
    default=[],
    multiple=True,
    help="Labels to set on the PR. Can be repeated",
)

pr_batch_size = click.option(
    "--pr-batch-size",
    metavar="COUNT",
    default=10,
    type=int,
    show_default=True,
    help="Number of PRs to create before pausing"
    + "Tune this parameter if your sync job hits the GitHub secondary rate limit.",
)

github_pause = click.option(
    "--github-pause",
    metavar="DURATION",
    default=120,
    type=int,
    show_default=True,
    help="Duration for which to pause (in seconds) after creating a number PRs "
    + "(according to --pr-batch-size). "
    + "Tune this parameter if your sync job hits the GitHub secondary rate limit.",
)

dependency_filter = click.option(
    "--filter",
    metavar="REGEX",
    default="",
    type=str,
    show_default=False,
    help="Regex to select which dependencies to sync. "
    + "If the option isn't given, all dependencies listed in the provided YAML "
    + "are synced.",
)


def local(help: str):
    return click.option(
        "--local",
        is_flag=True,
        default=False,
        help=help,
    )


def dry_run(help: str):
    return click.option(
        "--dry-run",
        is_flag=True,
        help=help,
        default=False,
    )
