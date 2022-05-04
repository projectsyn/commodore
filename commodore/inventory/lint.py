from __future__ import annotations

import abc

from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol

import click
import yaml

from commodore.config import Config
from commodore.helpers import yaml_load_all


from .lint_dependency_specification import lint_components, lint_packages
from .lint_deprecated_parameters import lint_deprecated_parameters


class LintFunc(Protocol):
    def __call__(self, file: Path, filecontents: dict[str, Any]) -> int:
        ...


class Linter:
    @abc.abstractmethod
    def __call__(self, config: Config, path: Path) -> int:
        ...


class ComponentSpecLinter(Linter):
    def __call__(self, config: Config, path: Path) -> int:
        return run_linter(config, path, lint_components)


class DeprecatedParameterLinter(Linter):
    def __call__(self, config: Config, path: Path) -> int:
        return run_linter(config, path, lint_deprecated_parameters)


class PackageSpecLinter(Linter):
    def __call__(self, config: Config, path: Path) -> int:
        return run_linter(config, path, lint_packages)


LINTERS = {
    "components": ComponentSpecLinter(),
    "deprecated-parameters": DeprecatedParameterLinter(),
    "packages": PackageSpecLinter(),
}


def _lint_file(cfg: Config, file: Path, lintfunc: LintFunc) -> int:
    errcount = 0
    try:
        filecontents = yaml_load_all(file)
        if len(filecontents) == 0:
            if cfg.debug:
                click.echo(f"> Skipping empty file {file}")
        elif len(filecontents) > 1:
            if cfg.debug:
                click.echo(
                    f"> Skipping file {file}: Linting multi-document YAML streams is not supported",
                )
        elif not isinstance(filecontents[0], dict):
            if cfg.debug:
                click.echo(
                    f"> Skipping file {file}: Expected top-level dictionary in YAML document"
                )
        else:
            errcount = lintfunc(file, filecontents[0])

    except (yaml.YAMLError, UnicodeDecodeError) as e:
        if cfg.debug:
            click.echo(f"> Skipping file {file}: Unable to load as YAML: {e}")

    return errcount


def _lint_directory(cfg: Config, path: Path, lintfunc: LintFunc) -> int:
    if not path.is_dir():
        raise ValueError("Unexpected path argument: expected to be a directory")

    errcount = 0
    for dentry in path.iterdir():
        if dentry.stem.startswith("."):
            if cfg.debug:
                click.echo(f"> Skipping hidden directory entry {dentry}")
            continue
        if dentry.is_dir():
            errcount += _lint_directory(cfg, dentry, lintfunc)
        else:
            errcount += _lint_file(cfg, dentry, lintfunc)
    return errcount


def run_linter(cfg: Config, path: Path, lintfunc: LintFunc) -> int:
    """Run lint function `lintfunc` in `path`.

    If `path` is a directory, run the function in all `.ya?ml` files in the directory
    (recursively).
    If `path` is a file, run the lint function in that file, if it's a YAML file.

    Returns a value that can be used as exit code to indicate whether there were linting
    errors.
    """
    if path.is_dir():
        return _lint_directory(cfg, path, lintfunc)

    return _lint_file(cfg, path, lintfunc)


def check_removed_reclass_variables(
    config: Config, location: str, paths: Iterable[Path]
):
    lint = DeprecatedParameterLinter()

    errcount = 0
    for path in paths:
        errcount += lint(config, path)

    # Raise error if any linting errors occurred
    if errcount > 0:
        raise click.ClickException(
            f"Found {errcount} usages of removed reclass variables "
            + f"in the {location}. See individual lint errors for details."
        )
