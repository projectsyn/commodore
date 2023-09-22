from __future__ import annotations

import os
import json
from collections.abc import Iterable
from pathlib import Path
from subprocess import call  # nosec
from typing import Optional

import click

from commodore.config import Config


def jsonnet_dependencies(config: Config) -> Iterable:
    """
    Creates a list of Jsonnet dependencies for the given Components.
    """
    dependencies = []

    for (_, component) in sorted(config.get_components().items()):
        dependencies.append(
            {
                "source": {
                    "local": {
                        "directory": os.path.relpath(
                            # TODO: Update again when we have proper monorepo handling
                            component.repo_directory,
                            start=config.work_dir,
                        ),
                    }
                }
            }
        )

    # Defining the `lib` folder as a local dependency is just a cheap way to have a symlink to that
    # folder.
    dependencies.append(
        {
            "source": {
                "local": {
                    "directory": os.path.relpath(
                        config.inventory.lib_dir, start=config.work_dir
                    ),
                }
            }
        }
    )

    return dependencies


def write_jsonnetfile(file: Path, deps: Iterable):
    """
    Writes the file `jsonnetfile.json` containing all provided dependencies.
    """
    data = {
        "version": 1,
        "dependencies": deps,
        "legacyImports": True,
    }

    with open(file, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, indent=4))
        f.write("\n")


def fetch_jsonnet_libraries(cwd: Path, deps: Optional[Iterable] = None):
    """
    Download Jsonnet libraries using Jsonnet-Bundler.
    """
    jsonnetfile = cwd / "jsonnetfile.json"
    if deps:
        write_jsonnetfile(jsonnetfile, deps)

    if not jsonnetfile.exists():
        click.secho("No jsonnetfile.json found, skipping Jsonnet Bundler install.")
        return

    try:
        # To make sure we don't use any stale lock files
        lock_file = cwd / "jsonnetfile.lock.json"
        if lock_file.exists():
            lock_file.unlink()
        if call(["jb", "install"], cwd=cwd) != 0:
            raise click.ClickException("jsonnet-bundler exited with error")
    except FileNotFoundError as e:
        raise click.ClickException(
            "the jsonnet-bundler executable `jb` could not be found"
        ) from e
