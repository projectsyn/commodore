"""Commands which interact with components"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import timedelta
from pathlib import Path
from typing import Optional

import click

from commodore.component import Component
from commodore.component.compile import compile_component
from commodore.component.template import ComponentTemplater
from commodore.config import Config
from commodore.dependency_syncer import sync_dependencies

import commodore.cli.options as options


@click.group(
    name="component",
    short_help="Interact with components.",
)
@options.verbosity
@options.pass_config
def component_group(config: Config, verbose):
    config.update_verbosity(verbose)


@component_group.command(name="new", short_help="Bootstrap a new component.")
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
@click.option(
    "--golden-tests/--no-golden-tests",
    default=True,
    show_default=True,
    help="Add golden tests to the component.",
)
@click.option(
    "--matrix-tests/--no-matrix-tests",
    default=True,
    show_default=True,
    help="Enable test matrix for compile/golden tests.",
)
@click.option(
    "--output-dir",
    default="",
    show_default=True,
    type=click.Path(file_okay=False, dir_okay=True),
    help="The directory in which to place the new component.",
)
@click.option(
    "--template-url",
    default="https://github.com/projectsyn/commodore-component-template.git",
    show_default=True,
    help="The URL of the component cookiecutter template.",
)
@click.option(
    "--template-version",
    default="main",
    show_default=True,
    help="The component template version (Git tree-ish) to use.",
)
@click.option(
    "--additional-test-case",
    "-t",
    metavar="CASE",
    default=[],
    show_default=True,
    multiple=True,
    help="Additional test cases to generate in the new component. Can be repeated. "
    + "Test case `defaults` will always be generated."
    + "Commodore will deduplicate test cases by name.",
)
@options.verbosity
@options.pass_config
# pylint: disable=too-many-arguments
def component_new(
    config: Config,
    slug: str,
    name: str,
    lib: bool,
    pp: bool,
    owner: str,
    copyright_holder: str,
    golden_tests: bool,
    matrix_tests: bool,
    verbose: int,
    output_dir: str,
    template_url: str,
    template_version: str,
    additional_test_case: Iterable[str],
):
    config.update_verbosity(verbose)
    t = ComponentTemplater(
        config, template_url, template_version, slug, name=name, output_dir=output_dir
    )
    t.library = lib
    t.post_process = pp
    t.github_owner = owner
    t.copyright_holder = copyright_holder
    t.golden_tests = golden_tests
    t.matrix_tests = matrix_tests
    t.test_cases = ["defaults"] + list(additional_test_case)
    t.create()


@component_group.command(
    name="update", short_help="Update an existing component from a template"
)
@click.argument(
    "component_path", type=click.Path(exists=True, dir_okay=True, file_okay=False)
)
@click.option(
    "--copyright",
    "copyright_holder",
    show_default=True,
    help="Update the copyright holder in the license file.",
)
@click.option(
    "--update-copyright-year/--no-update-copyright-year",
    default=False,
    show_default=True,
    help="Update year in copyright notice.",
)
@click.option(
    "--golden-tests/--no-golden-tests",
    default=None,
    show_default=True,
    help="Add or remove golden tests.",
)
@click.option(
    "--matrix-tests/--no-matrix-tests",
    default=None,
    show_default=True,
    help="Add or remove matrix tests.",
)
@click.option(
    "--lib/--no-lib",
    default=None,
    show_default=True,
    help="Add or remove the component library.",
)
@click.option(
    "--pp/--no-pp",
    default=None,
    show_default=True,
    help="Add or remove the postprocessing filter configuration.",
)
@click.option(
    "--additional-test-case",
    "-t",
    metavar="CASE",
    default=[],
    show_default=True,
    multiple=True,
    help="Additional test cases to add to the component. Can be repeated. "
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
def component_update(
    config: Config,
    verbose: int,
    component_path: str,
    copyright_holder: str,
    golden_tests: Optional[bool],
    matrix_tests: Optional[bool],
    lib: Optional[bool],
    pp: Optional[bool],
    update_copyright_year: bool,
    additional_test_case: Iterable[str],
    remove_test_case: Iterable[str],
    commit: bool,
):
    """This command updates the component at COMPONENT_PATH to the latest version of the
    template which was originally used to create it, if the template version is given as
    a Git branch.

    The command will never commit `.rej` or `.orig` files which result from template
    updates which couldn't be applied cleanly.

    The command can also add or remove component features, based on the provided command
    line options.
    """
    config.update_verbosity(verbose)

    t = ComponentTemplater.from_existing(config, Path(component_path))
    if copyright_holder:
        t.copyright_holder = copyright_holder
    if update_copyright_year:
        t.copyright_year = None
    if golden_tests is not None:
        t.golden_tests = golden_tests
    if matrix_tests is not None:
        t.matrix_tests = matrix_tests
    if lib is not None:
        t.library = lib
    if pp is not None:
        t.post_process = pp

    test_cases = t.test_cases
    test_cases.extend(additional_test_case)
    t.test_cases = [tc for tc in test_cases if tc not in remove_test_case]

    t.update(commit=commit)


@component_group.command(name="delete", short_help="Remove component from inventory.")
@click.argument("slug")
@click.option(
    "--force/--no-force",
    default=False,
    show_default=True,
    help="Don't prompt for user confirmation when deleting.",
)
@options.verbosity
@options.pass_config
# pylint: disable=too-many-arguments
def component_delete(config: Config, slug, force, verbose):
    config.update_verbosity(verbose)
    config.force = force
    f = ComponentTemplater(config, "", None, slug)
    f.delete()


@component_group.command(name="compile", short_help="Compile a single component.")
@click.argument("path", type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option(
    "-f",
    "--values",
    multiple=True,
    type=click.Path(exists=True, file_okay=True, dir_okay=False),
    help="Specify inventory class in a YAML file (can specify multiple).",
)
@click.option(
    "-a",
    "--alias",
    metavar="ALIAS",
    help="Provide component alias to use when compiling component.",
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
@click.option(
    "-r",
    "--repo-directory",
    default="",
    show_default=False,
    type=click.Path(file_okay=False, dir_okay=True),
    help="DEPRECATED.  This option has no effect anymore.",
)
@click.option(
    "-n",
    "--name",
    default="",
    show_default=False,
    help="Component name to use for Commodore. "
    + "If not provided, the name is inferred from the Git repository name.",
)
@options.verbosity
@options.pass_config
# pylint: disable=too-many-arguments
def component_compile(
    config: Config,
    path: str,
    values: Iterable[str],
    alias: Optional[str],
    search_paths: Iterable[str],
    output: str,
    repo_directory: str,
    name: str,
    verbose: int,
):
    config.update_verbosity(verbose)
    if repo_directory:
        click.secho(
            " > Parameter `-r`/`--repo-directory` is deprecated and has no effect"
        )

    compile_component(config, path, alias, values, search_paths, output, name)


@component_group.command("sync", short_help="Synchronize components to template")
@options.verbosity
@options.pass_config
@click.argument(
    "component_list", type=click.Path(file_okay=True, dir_okay=False, exists=True)
)
@options.dry_run("Don't commit rendered changes, or create or update PRs")
@options.github_token
@options.pr_branch
@options.pr_label
@options.pr_batch_size
@options.github_pause
@options.dependency_filter
def component_sync(
    config: Config,
    verbose: int,
    component_list: str,
    github_token: str,
    dry_run: bool,
    pr_branch: str,
    pr_label: Iterable[str],
    pr_batch_size: int,
    github_pause: int,
    filter: str,
):
    """This command processes all components listed in the provided `COMPONENT_LIST`
    YAML file.

    Currently, the command only supports updating components hosted on GitHub. The
    command expects that the YAML file contains a single document with a list of GitHub
    repositories in form `organization/repository-name`.

    The command supports selectively updating components through parameter `--filter`.
    This parameter enables callers to filter the list provided in the YAML file by an
    arbitrary regex.

    The command clones each component and runs `component update` on the local copy. If
    there are any changes, the command creates a PR for the changes. For each component,
    the command parses the component's `.cruft.json` to determine the template repository
    and template version for the component. The command bases each PR on the default
    branch of the corresponding component repository as reported by the GitHub API.

    The command requires a GitHub Access token with the 'public_repo' permission, which
    is required to create PRs on public repositories. If you want to manage private
    repos, the access token may require additional permissions.
    """
    config.update_verbosity(verbose)
    config.github_token = github_token

    sync_dependencies(
        config,
        Path(component_list),
        dry_run,
        pr_branch,
        pr_label,
        Component,
        ComponentTemplater,
        pr_batch_size,
        timedelta(seconds=github_pause),
        filter,
    )
