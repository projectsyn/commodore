"""Commands which interact with components"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import timedelta
from pathlib import Path
from typing import Optional, Tuple

import click

from commodore.component import Component
from commodore.component.compile import compile_component
from commodore.component.template import ComponentTemplater
from commodore.config import Config
from commodore.dependency_syncer import sync_dependencies

import commodore.cli.options as options


def _generate_option_text_snippets(new_cmd: bool) -> Tuple[str, str]:
    if new_cmd:
        test_case_help = (
            "Additional test cases to generate in the new component. "
            + "Can be repeated. Test case `defaults` will always be generated. "
            + "Commodore will deduplicate test cases by name."
        )
    else:
        test_case_help = (
            "Additional test cases to add to the component. Can be repeated. "
            + "Commodore will deduplicate test cases by name."
        )
    add_text = "Add" if new_cmd else "Add or remove"

    return add_text, test_case_help


def _generate_automerge_pattern_help(level: str, remove: bool = False) -> str:
    op = "remove" if remove else "add"
    opc = op.capitalize()
    if remove:
        removenote = (
            "This flag has no effect if the provided pattern isn't part of the "
            + "currently configured patterns. "
        )
    else:
        removenote = ""
    if level == "patch":
        return (
            f"{opc} regex pattern for dependencies that should be excluded from "
            + "automerging of patch updates. Can be repeated. Commodore will "
            + "deduplicate patterns. "
            + removenote
            + f"See '--{op}-automerge-patch-block-depname' for a variant of this flag "
            + "which allows specifying dependency names."
        )
    if level == "patch_v0":
        return (
            f"{opc} regex pattern for dependencies with current version v0.x for which "
            + "patch updates should be automerged. This flag has no effect if "
            + "automerging for patch updates for v0.x dependencies is enabled via "
            + "'--automerge-patch-v0'. Can be repeated. Commodore will deduplicate "
            + "patterns. "
            + removenote
            + f"See '--{op}-automerge-patch-v0-allow-depname' for a variant of "
            + "this flag which allows specifying dependency names."
        )
    if level == "minor":
        return (
            f"{opc} regex pattern for dependencies for which minor updates should be "
            + "automerged. Can be repeated. Commodore will deduplicate patterns. "
            + removenote
            + f"See '--{op}-automerge-minor-allow-depname' for a variant of "
            + "this flag which allows specifying dependency names."
        )

    raise ValueError(
        f"Expected 'level' to be one of ['patch', 'patch_v0', 'minor'], got {level}"
    )


def _generate_automerge_depname_help(level: str, remove: bool = False) -> str:
    implnote = (
        "Commodore will convert the provided dependency names into a list of anchored "
        + "regex patterns."
    )
    op = "remove" if remove else "add"
    opc = op.capitalize()
    if remove:
        removenote = (
            "This flag has no effect if the provided name isn't part of the "
            + "currently configured dependency names. "
        )
    else:
        removenote = ""
    if level == "patch":
        return (
            f"{opc} dependency name that should be excluded from automerging of patch "
            + "updates. Can be repeated. Commodore will deduplicate dependency names. "
            + removenote
            + f"See '--{op}-automerge-patch-block-pattern' for a variant of this flag "
            + "which allows specifying regex patterns. "
            + implnote
        )
    if level == "patch_v0":
        return (
            f"{opc} name of dependency with current version v0.x for which patch updates "
            + "should be automerged. This flag has no effect if automerging for patch "
            + "updates for v0.x dependencies is enabled via '--automerge-patch-v0'. "
            + "Can be repeated. Commodore will deduplicate dependency names. "
            + removenote
            + f"See '--{op}-automerge-patch-v0-allow-pattern' for a variant of this "
            + "flag which allows specifying regex patterns. "
            + implnote
        )
    if level == "minor":
        return (
            f"{opc} dependency name for which minor updates should be automerged. "
            + "Can be repeated. Commodore will deduplicate dependency names. "
            + removenote
            + f"See '--{op}-automerge-minor-allow-pattern' for a variant of "
            + "this flag which allows specifying regex patterns. "
            + implnote
        )

    raise ValueError(
        f"Expected 'level' to be one of ['patch', 'patch_v0', 'minor'], got {level}"
    )


def new_update_options(new_cmd: bool):
    """Shared command options for component new and component update.

    Options will appear in `--help` in reverse order of the click.option() calls in this
    function.

    If flag `new_cmd` is set, default values will be set for options that are left
    unchanged by default by `component update`.
    """

    add_text, test_case_help = _generate_option_text_snippets(new_cmd)

    def decorator(cmd):
        click.option(
            "--add-automerge-minor-allow-pattern",
            metavar="PATTERN",
            default=[],
            show_default=True,
            multiple=True,
            help=_generate_automerge_pattern_help(level="minor"),
        )(cmd)
        click.option(
            "--add-automerge-minor-allow-depname",
            metavar="NAME",
            default=[],
            show_default=True,
            multiple=True,
            help=_generate_automerge_depname_help(level="minor"),
        )(cmd)
        click.option(
            "--add-automerge-patch-v0-allow-pattern",
            metavar="PATTERN",
            default=[],
            show_default=True,
            multiple=True,
            help=_generate_automerge_pattern_help(level="patch_v0"),
        )(cmd)
        click.option(
            "--add-automerge-patch-v0-allow-depname",
            metavar="NAME",
            default=[],
            show_default=True,
            multiple=True,
            help=_generate_automerge_depname_help(level="patch_v0"),
        )(cmd)
        click.option(
            "--add-automerge-patch-block-pattern",
            metavar="PATTERN",
            default=[],
            show_default=True,
            multiple=True,
            help=_generate_automerge_pattern_help(level="patch"),
        )(cmd)
        click.option(
            "--add-automerge-patch-block-depname",
            metavar="NAME",
            default=[],
            show_default=True,
            multiple=True,
            help=_generate_automerge_depname_help(level="patch"),
        )(cmd)
        click.option(
            "--autorelease / --no-autorelease",
            is_flag=True,
            default=True if new_cmd else None,
            help="Enable autorelease GitHub action. "
            + "When autorelease is enabled, new releases will be generated "
            + "for automerged dependency PRs.",
        )(cmd)
        click.option(
            "--automerge-patch-v0 / --no-automerge-patch-v0",
            is_flag=True,
            default=False if new_cmd else None,
            help="Enable automerging of patch-level dependency PRs "
            + "for v0.x dependencies.",
        )(cmd)
        click.option(
            "--automerge-patch / --no-automerge-patch",
            is_flag=True,
            default=True if new_cmd else None,
            help="Enable automerging of patch-level dependency PRs.",
        )(cmd)
        click.option(
            "--additional-test-case",
            "-t",
            metavar="CASE",
            default=[],
            show_default=True,
            multiple=True,
            help=test_case_help,
        )(cmd)
        click.option(
            "--matrix-tests/--no-matrix-tests",
            default=True if new_cmd else None,
            show_default=True,
            help=f"{add_text} test matrix for compile/golden tests.",
        )(cmd)
        click.option(
            "--golden-tests/--no-golden-tests",
            default=True if new_cmd else None,
            show_default=True,
            help=f"{add_text} golden tests.",
        )(cmd)
        click.option(
            "--pp/--no-pp",
            default=False if new_cmd else None,
            show_default=True,
            help=f"{add_text} postprocessing filter configuration.",
        )(cmd)
        click.option(
            "--lib/--no-lib",
            default=False if new_cmd else None,
            show_default=True,
            help=f"{add_text} the component library template.",
        )(cmd)
        click.option(
            "--copyright",
            "copyright_holder",
            default="VSHN AG <info@vshn.ch>" if new_cmd else "",
            show_default=True,
            help="The copyright holder added to the license file.",
        )(cmd)

        return cmd

    return decorator


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
    "--output-dir",
    default="",
    show_default=True,
    type=click.Path(file_okay=False, dir_okay=True),
    help="The directory in which to place the new component.",
)
@click.option(
    "--owner",
    default="projectsyn",
    show_default=True,
    help="The GitHub user or project name where the component will be hosted.",
)
@click.option(
    "--template-url",
    default="https://github.com/projectsyn/commodore-component-template.git",
    show_default=True,
    help="The URL of the component cookiecutter template.",
)
@options.template_version("main")
@new_update_options(new_cmd=True)
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
    automerge_patch: bool,
    automerge_patch_v0: bool,
    autorelease: bool,
    add_automerge_patch_block_depname: Iterable[str],
    add_automerge_patch_block_pattern: Iterable[str],
    add_automerge_patch_v0_allow_depname: Iterable[str],
    add_automerge_patch_v0_allow_pattern: Iterable[str],
    add_automerge_minor_allow_depname: Iterable[str],
    add_automerge_minor_allow_pattern: Iterable[str],
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
    t.automerge_patch = automerge_patch
    t.automerge_patch_v0 = automerge_patch_v0
    t.autorelease = autorelease
    for name in add_automerge_patch_block_depname:
        t.add_automerge_patch_block_depname(name)
    for pattern in add_automerge_patch_block_pattern:
        t.add_automerge_patch_block_pattern(pattern)
    for name in add_automerge_patch_v0_allow_depname:
        t.add_automerge_patch_v0_allow_depname(name)
    for pattern in add_automerge_patch_v0_allow_pattern:
        t.add_automerge_patch_v0_allow_pattern(pattern)
    for name in add_automerge_minor_allow_depname:
        t.add_automerge_minor_allow_depname(name)
    for pattern in add_automerge_minor_allow_pattern:
        t.add_automerge_minor_allow_pattern(pattern)
    t.create()


@component_group.command(
    name="update", short_help="Update an existing component from a template"
)
@click.argument(
    "component_path", type=click.Path(exists=True, dir_okay=True, file_okay=False)
)
@click.option(
    "--update-copyright-year/--no-update-copyright-year",
    default=False,
    show_default=True,
    help="Update year in copyright notice.",
)
@new_update_options(new_cmd=False)
@click.option(
    "--remove-test-case",
    metavar="CASE",
    default=[],
    show_default=True,
    multiple=True,
    help="Test cases to remove from the component. Can be repeated.",
)
@click.option(
    "--remove-automerge-patch-block-depname",
    metavar="NAME",
    default=[],
    show_default=True,
    multiple=True,
    help=_generate_automerge_depname_help(level="patch", remove=True),
)
@click.option(
    "--remove-automerge-patch-block-pattern",
    metavar="PATTERN",
    default=[],
    show_default=True,
    multiple=True,
    help=_generate_automerge_pattern_help(level="patch", remove=True),
)
@click.option(
    "--remove-automerge-patch-v0-allow-depname",
    metavar="NAME",
    default=[],
    show_default=True,
    multiple=True,
    help=_generate_automerge_depname_help(level="patch_v0", remove=True),
)
@click.option(
    "--remove-automerge-patch-v0-allow-pattern",
    metavar="PATTERN",
    default=[],
    show_default=True,
    multiple=True,
    help=_generate_automerge_pattern_help(level="patch_v0", remove=True),
)
@click.option(
    "--remove-automerge-minor-allow-depname",
    metavar="NAME",
    default=[],
    show_default=True,
    multiple=True,
    help=_generate_automerge_depname_help(level="minor", remove=True),
)
@click.option(
    "--remove-automerge-minor-allow-pattern",
    metavar="PATTERN",
    default=[],
    show_default=True,
    multiple=True,
    help=_generate_automerge_pattern_help(level="minor", remove=True),
)
@click.option(
    "--commit / --no-commit",
    is_flag=True,
    default=True,
    help="Whether to commit the rendered template changes.",
)
@options.template_version(None)
@options.verbosity
@options.pass_config
def component_update(
    config: Config,
    verbose: int,
    component_path: str,
    copyright_holder: str,
    template_version: Optional[str],
    golden_tests: Optional[bool],
    matrix_tests: Optional[bool],
    lib: Optional[bool],
    pp: Optional[bool],
    update_copyright_year: bool,
    additional_test_case: Iterable[str],
    remove_test_case: Iterable[str],
    commit: bool,
    automerge_patch: Optional[bool],
    automerge_patch_v0: Optional[bool],
    autorelease: Optional[bool],
    add_automerge_patch_block_depname: Iterable[str],
    add_automerge_patch_block_pattern: Iterable[str],
    add_automerge_patch_v0_allow_depname: Iterable[str],
    add_automerge_patch_v0_allow_pattern: Iterable[str],
    add_automerge_minor_allow_depname: Iterable[str],
    add_automerge_minor_allow_pattern: Iterable[str],
    remove_automerge_patch_block_depname: Iterable[str],
    remove_automerge_patch_block_pattern: Iterable[str],
    remove_automerge_patch_v0_allow_depname: Iterable[str],
    remove_automerge_patch_v0_allow_pattern: Iterable[str],
    remove_automerge_minor_allow_depname: Iterable[str],
    remove_automerge_minor_allow_pattern: Iterable[str],
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
    if automerge_patch is not None:
        t.automerge_patch = automerge_patch
    if automerge_patch_v0 is not None:
        t.automerge_patch_v0 = automerge_patch_v0
    if autorelease is not None:
        t.autorelease = autorelease
    if template_version is not None:
        t.template_version = template_version

    test_cases = t.test_cases
    test_cases.extend(additional_test_case)
    t.test_cases = [tc for tc in test_cases if tc not in remove_test_case]

    for name in add_automerge_patch_block_depname:
        t.add_automerge_patch_block_depname(name)
    for pattern in add_automerge_patch_block_pattern:
        t.add_automerge_patch_block_pattern(pattern)
    for name in add_automerge_patch_v0_allow_depname:
        t.add_automerge_patch_v0_allow_depname(name)
    for pattern in add_automerge_patch_v0_allow_pattern:
        t.add_automerge_patch_v0_allow_pattern(pattern)
    for name in add_automerge_minor_allow_depname:
        t.add_automerge_minor_allow_depname(name)
    for pattern in add_automerge_minor_allow_pattern:
        t.add_automerge_minor_allow_pattern(pattern)

    for name in remove_automerge_patch_block_depname:
        t.remove_automerge_patch_block_depname(name)
    for pattern in remove_automerge_patch_block_pattern:
        t.remove_automerge_patch_block_pattern(pattern)
    for name in remove_automerge_patch_v0_allow_depname:
        t.remove_automerge_patch_v0_allow_depname(name)
    for pattern in remove_automerge_patch_v0_allow_pattern:
        t.remove_automerge_patch_v0_allow_pattern(pattern)
    for name in remove_automerge_minor_allow_depname:
        t.remove_automerge_minor_allow_depname(name)
    for pattern in remove_automerge_minor_allow_pattern:
        t.remove_automerge_minor_allow_pattern(pattern)

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
@options.template_version(None)
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
    template_version: Optional[str],
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
        template_version,
    )
