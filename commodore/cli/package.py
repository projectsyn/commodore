"""Commands which interact with config packages"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import timedelta
from pathlib import Path
from typing import Optional

import click

from commodore.config import Config
from commodore.dependency_syncer import sync_dependencies
from commodore.package import Package
from commodore.package.compile import compile_package
from commodore.package.template import PackageTemplater

import commodore.cli.options as options


@click.group(
    name="package",
    short_help="Interact with a Commodore config package",
)
@options.verbosity
@options.pass_config
def package_group(config: Config, verbose: int):
    config.update_verbosity(verbose)


@package_group.command(
    name="new", short_help="Create a new config package from a template"
)
@click.argument("slug")
@click.option(
    "--name",
    help="The package's name as it will be written in the documentation. Defaults to the slug.",
)
@click.option(
    "--owner",
    default="projectsyn",
    show_default=True,
    help="The GitHub user or project name where the package will be hosted.",
)
@click.option(
    "--copyright",
    "copyright_holder",
    default="VSHN AG <info@vshn.ch>",
    show_default=True,
    help="The copyright holder added to the license file.",
)
@click.option(
    "--golden-tests/--no-golden-tests",
    default=True,
    show_default=True,
    help="Add golden tests to the package.",
)
@click.option(
    "--template-url",
    default="https://github.com/projectsyn/commodore-config-package-template.git",
    show_default=True,
    help="The URL of the package cookiecutter template.",
)
@click.option(
    "--template-version",
    default="main",
    show_default=True,
    help="The package template version (Git tree-ish) to use.",
)
@click.option(
    "--output-dir",
    default="",
    show_default=True,
    type=click.Path(file_okay=False, dir_okay=True),
    help="The directory in which to place the new package.",
)
@click.option(
    "--additional-test-case",
    "-t",
    metavar="CASE",
    default=[],
    show_default=True,
    multiple=True,
    help="Additional test cases to generate in the new package. Can be repeated. "
    + "Test case `defaults` will always be generated."
    + "Commodore will deduplicate test cases by name.",
)
@options.verbosity
@options.pass_config
# pylint: disable=too-many-arguments
def package_new(
    config: Config,
    verbose: int,
    slug: str,
    name: Optional[str],
    owner: str,
    copyright_holder: str,
    golden_tests: bool,
    template_url: str,
    template_version: str,
    output_dir: str,
    additional_test_case: Iterable[str],
):
    """Create new config package repo from template.

    The command line options allow the caller to customize the remote repository
    location (only supports GitHub at the moment), the package's display name, whether
    to configure golden tests, and the licensing details.
    """
    config.update_verbosity(verbose)
    t = PackageTemplater(
        config, template_url, template_version, slug, name=name, output_dir=output_dir
    )
    t.github_owner = owner
    t.copyright_holder = copyright_holder
    t.golden_tests = golden_tests
    t.test_cases = ["defaults"] + list(additional_test_case)
    t.create()


@package_group.command(
    name="update", short_help="Update an existing config package from a template"
)
@click.argument(
    "package_path", type=click.Path(exists=True, dir_okay=True, file_okay=False)
)
@click.option(
    "--copyright",
    "copyright_holder",
    show_default=True,
    help="The copyright holder added to the license file.",
)
@click.option(
    "--golden-tests/--no-golden-tests",
    default=None,
    show_default=True,
    help="Add golden tests to the package.",
)
@click.option(
    "--update-copyright-year/--no-update-copyright-year",
    default=False,
    show_default=True,
    help="Update year in copyright notice.",
)
@click.option(
    "--additional-test-case",
    "-t",
    metavar="CASE",
    default=[],
    show_default=True,
    multiple=True,
    help="Additional test cases to generate in the new package. Can be repeated. "
    + "Already existing test cases will always be kept. "
    + "Commodore will deduplicate test cases by name.",
)
@click.option(
    "--remove-test-case",
    metavar="CASE",
    default=[],
    show_default=True,
    multiple=True,
    help="Test cases to remove from the package. Can be repeated.",
)
@click.option(
    "--commit / --no-commit",
    is_flag=True,
    default=True,
    help="Whether to commit the rendered template changes.",
)
@options.verbosity
@options.pass_config
# pylint: disable=too-many-arguments
def package_update(
    config: Config,
    verbose: int,
    package_path: str,
    copyright_holder: Optional[str],
    golden_tests: Optional[bool],
    update_copyright_year: bool,
    additional_test_case: Iterable[str],
    remove_test_case: Iterable[str],
    commit: bool,
):
    """This command updates the package at PACKAGE_PATH to the latest version of the
    template which was originally used to create it, if the template version is given as
    a Git branch.

    The command will never commit `.rej` or `.orig` files which result from template
    updates which couldn't be applied cleanly.

    The command can also add or remove package features, based on the provided command
    line options.
    """
    config.update_verbosity(verbose)
    t = PackageTemplater.from_existing(config, Path(package_path))

    # Add provided values
    if copyright_holder:
        t.copyright_holder = copyright_holder
    if golden_tests is not None:
        t.golden_tests = golden_tests
    if update_copyright_year:
        t.copyright_year = None
    test_cases = t.test_cases
    test_cases.extend(additional_test_case)
    t.test_cases = [tc for tc in test_cases if tc not in remove_test_case]

    t.update(commit=commit)


@package_group.command(name="compile", short_help="Compile a config package standalone")
@click.argument("path", type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.argument(
    "test_class", type=click.Path(exists=False, file_okay=True, dir_okay=False)
)
@click.option(
    "-f",
    "--values",
    multiple=True,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    help="Specify additional inventory class in a YAML file (can specify multiple).",
)
@options.local(
    "Run in local mode, local mode reuses the contents of the working directory. "
    + "Local mode won't fetch missing components."
)
@click.option(
    " / -F",
    "--fetch-dependencies/--no-fetch-dependencies",
    default=True,
    help="Whether to fetch Jsonnet and Kapitan dependencies in local mode. "
    + "By default dependencies are fetched.",
)
@click.option(
    "-k / ",
    "--keep-dir/--no-keep-dir",
    default=False,
    show_default=True,
    help="Whether to keep the compilation temp directory after the compilation is done.",
)
@click.option(
    "--tmp-dir",
    default="",
    metavar="PATH",
    type=click.Path(exists=False, file_okay=False, dir_okay=True),
    help="Temp directory to use for compilation. Implies `--keep-dir`",
)
@options.verbosity
@options.pass_config
# pylint: disable=too-many-arguments
def package_compile(
    config: Config,
    verbose: int,
    path: str,
    test_class: str,
    values: Iterable[str],
    local: bool,
    fetch_dependencies: bool,
    keep_dir: bool,
    tmp_dir: str,
):
    config.update_verbosity(verbose)
    config.local = local
    config.fetch_dependencies = fetch_dependencies
    compile_package(config, path, test_class, values, tmp_dir, keep_dir)


@package_group.command("sync", short_help="Synchronize packages to template")
@options.verbosity
@options.pass_config
@click.argument(
    "package_list", type=click.Path(file_okay=True, dir_okay=False, exists=True)
)
@options.dry_run("Don't commit rendered changes, or create or update PRs")
@options.github_token
@options.pr_branch
@options.pr_label
@options.pr_batch_size
@options.github_pause
@options.dependency_filter
def package_sync(
    config: Config,
    verbose: int,
    package_list: str,
    github_token: str,
    dry_run: bool,
    pr_branch: str,
    pr_label: Iterable[str],
    pr_batch_size: int,
    github_pause: int,
    filter: str,
):
    """This command processes all packages listed in the provided `PACKAGE_LIST` YAML file.

    Currently, the command only supports updating packages hosted on GitHub. The command
    expects that the YAML file contains a single document with a list of GitHub
    repositories in form `organization/repository-name`.

    The command supports selectively updating components through parameter `--filter`.
    This parameter enables callers to filter the list provided in the YAML file by an
    arbitrary regex.

    The command clones each package and runs `package update` on the local copy. If
    there are any changes, the command creates a PR for the changes. For each package,
    the command parses the package's `.cruft.json` to determine the template repository
    and template version for the package. The command bases each PR on the default
    branch of the corresponding package repository as reported by the GitHub API.

    The command requires a GitHub Access token with the 'public_repo' permission, which
    is required to create PRs on public repositories. If you want to manage private
    repos, the access token may require additional permissions.
    """
    config.update_verbosity(verbose)
    config.github_token = github_token

    sync_dependencies(
        config,
        Path(package_list),
        dry_run,
        pr_branch,
        pr_label,
        Package,
        PackageTemplater,
        pr_batch_size,
        timedelta(seconds=github_pause),
        filter,
    )
