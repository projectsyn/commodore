from __future__ import annotations

import abc
import glob

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
    def __call__(
        self, config: Config, path: Path, ignore_patterns: tuple[str, ...] = ()
    ) -> int:
        ...


class ComponentSpecLinter(Linter):
    def __call__(
        self, config: Config, path: Path, ignore_patterns: tuple[str, ...] = ()
    ) -> int:
        return run_linter(config, path, ignore_patterns, lint_components)


class DeprecatedParameterLinter(Linter):
    def __call__(
        self, config: Config, path: Path, ignore_patterns: tuple[str, ...] = ()
    ) -> int:
        return run_linter(config, path, ignore_patterns, lint_deprecated_parameters)


class PackageSpecLinter(Linter):
    def __call__(
        self, config: Config, path: Path, ignore_patterns: tuple[str, ...] = ()
    ) -> int:
        return run_linter(config, path, ignore_patterns, lint_packages)


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


def _lint_directory(
    cfg: Config, path: Path, ignore_paths: set[Path], lintfunc: LintFunc
) -> int:
    if not path.is_dir():
        raise ValueError("Unexpected path argument: expected to be a directory")

    errcount = 0
    for dentry in path.iterdir():
        if dentry.stem.startswith("."):
            if cfg.debug:
                click.echo(f"> Skipping hidden directory entry {dentry}")
            continue
        if dentry.absolute() in ignore_paths:
            if cfg.debug:
                click.echo(f"> Skipping ignored directory entry {dentry}")
            continue
        if dentry.is_dir():
            errcount += _lint_directory(cfg, dentry, ignore_paths, lintfunc)
        else:
            errcount += _lint_file(cfg, dentry, lintfunc)
    return errcount


def _read_ignore_patterns_from_file(path: Path) -> set[str]:
    ignore_patterns = set()
    if path.is_file():
        with open(path, "r", encoding="utf-8") as ifile:
            for p in ifile.readlines():
                ignore_patterns.add(p.strip())

    return ignore_patterns


def _render_ignore_patterns(
    base_dir: Path, ignore_patterns: tuple[str, ...]
) -> set[Path]:
    """Use `glob.glob()` to render the paths to ignore from `ignore_patterns`.
    All patterns are rooted at `base_dir`.

    If pattern doesn't start with /, we will treat it as matching any prefix in
    `base_dir`."""

    # Read additional ignore patterns from `<base_dir>/.commodoreignore`, if the file
    # exists
    _ignore_patterns = set(ignore_patterns)
    # Extend ignore patterns set with ignore patterns from `.commodoreignore`
    _ignore_patterns |= _read_ignore_patterns_from_file(base_dir / ".commodoreignore")

    ignore_paths: set[str] = set()
    for pat in _ignore_patterns:
        if pat.startswith("/"):
            pat = f"{base_dir.absolute()}{pat}"
        else:
            pat = f"{base_dir.absolute()}/**/{pat}"
        ignore_paths |= set(glob.glob(pat, recursive=True))

    return {Path(p) for p in ignore_paths}


def run_linter(
    cfg: Config, path: Path, ignore_patterns: tuple[str, ...], lintfunc: LintFunc
) -> int:
    """Run lint function `lintfunc` in `path`.

    If `path` is a directory, run the function in all `.ya?ml` files in the directory
    (recursively).
    If `path` is a file, run the lint function in that file, if it's a YAML file.

    Returns a value that can be used as exit code to indicate whether there were linting
    errors.
    """
    base_dir = path.absolute()
    if not base_dir.is_dir():
        base_dir = path.parent
    ignore_paths = _render_ignore_patterns(base_dir, ignore_patterns)

    if path.absolute() in ignore_paths:
        if cfg.debug:
            click.echo(f" > Skipping ignored path {path}")
        return 0

    if path.is_dir():
        return _lint_directory(cfg, path, ignore_paths, lintfunc)

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
