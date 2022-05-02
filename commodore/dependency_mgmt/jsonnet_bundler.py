from __future__ import annotations

import os
import json
from collections.abc import Iterable
from pathlib import Path
from subprocess import call  # nosec

import click

from commodore.config import Config
from commodore.helpers import relsymlink


def jsonnet_dependencies(config: Config) -> Iterable:
    """
    Creates a list of Jsonnet dependencies for the given Components.
    """
    dependencies = []

    for component in config.get_components().values():
        dependencies.append(
            {
                "source": {
                    "local": {
                        "directory": os.path.relpath(
                            component.target_directory, start=config.work_dir
                        ),
                    }
                }
            }
        )

    # Defining the `lib` folder as a local dependency is just a cheap way to have a symlink to that folder.
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


def fetch_jsonnet_libraries(cwd: Path, deps: Iterable = None):
    """
    Download Jsonnet libraries using Jsonnet-Bundler.
    """
    jsonnetfile = cwd / "jsonnetfile.json"
    if not jsonnetfile.exists() or deps:
        if not deps:
            deps = []
        write_jsonnetfile(jsonnetfile, deps)

    inject_essential_libraries(jsonnetfile)

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

    # Link essential libraries for backwards compatibility.
    lib_dir = (cwd / "vendor" / "lib").resolve()
    lib_dir.mkdir(exist_ok=True)
    relsymlink(
        cwd / "vendor" / "kube-libsonnet" / "kube.libsonnet", lib_dir, "kube.libjsonnet"
    )


def inject_essential_libraries(file: Path):
    """
    Ensures essential libraries are added to `jsonnetfile.json`.
    :param file: The path to `jsonnetfile.json`.
    """
    with open(file, "r", encoding="utf-8") as f:
        data = json.load(f)

    deps = data["dependencies"]
    has_kube = False
    for dep in deps:
        remote = dep.get("source", {}).get("git", {}).get("remote", "")
        has_kube = has_kube or "kube-libsonnet" in remote

    if not has_kube:
        deps.append(
            {
                "source": {
                    "git": {"remote": "https://github.com/bitnami-labs/kube-libsonnet"}
                },
                "version": "v1.19.0",
            },
        )

    with open(file, "w", encoding="utf-8") as j:
        json.dump(data, j, indent=4)
        j.write("\n")
