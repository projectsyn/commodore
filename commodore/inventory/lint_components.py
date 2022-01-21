from pathlib import Path
from typing import Dict

import click
import yaml

from commodore.config import Config
from commodore.helpers import yaml_load_all


def _lint_component_versions(file: Path, filecontents: Dict) -> int:
    errcount = 0
    components = filecontents.get("parameters", {}).get("components", {})
    for cn, cspec in components.items():
        if "version" not in cspec:
            click.secho(
                f"> Component specification for {cn} is missing explict version in {file}",
                fg="red",
            )
            errcount += 1
    return errcount


def _lint_file(cfg: Config, file: Path) -> int:
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
            errcount = _lint_component_versions(file, filecontents[0])

    except (yaml.YAMLError, UnicodeDecodeError) as e:
        if cfg.debug:
            click.echo(f"> Skipping file {file}: Unable to load as YAML: {e}")

    return errcount


def _lint_directory(cfg, path: Path) -> int:
    if not path.is_dir():
        raise ValueError("Unexpected path argument: expected to be a directory")

    errcount = 0
    for dentry in path.iterdir():
        if dentry.stem.startswith("."):
            if cfg.debug:
                click.echo(f"> Skipping hidden directory entry {dentry}")
            continue
        if dentry.is_dir():
            errcount += _lint_directory(cfg, dentry)
        else:
            errcount += _lint_file(cfg, dentry)
    return errcount


def lint_components(cfg: Config, path: Path) -> int:
    """Lint component specifications (`parameters.components`) in `path`.

    If `path` is a directory, lint `parameters.components` in all `.ya?ml` files in the
    directory (recursively).
    If `path` is a file, lint `parameters.components` in that file, if it's a YAML file.

    Returns a value that can be used as exit code to indicate whether there were linting
    errors.
    """
    if path.is_dir():
        return _lint_directory(cfg, path)

    return _lint_file(cfg, path)
