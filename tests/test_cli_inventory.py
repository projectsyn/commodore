from __future__ import annotations

import json

from pathlib import Path
from typing import Any

import pytest
import yaml

from conftest import RunnerFunc


@pytest.mark.parametrize(
    "files,exitcode,stdout",
    [
        ({}, 0, ["No errors"]),
        (
            {
                "test.yaml": {
                    "parameters": {
                        "components": {
                            "tc1": {
                                "url": "https://example.com/tc1.git",
                                "version": "v1.0.0",
                            },
                            "tc2": {
                                "url": "https://example.com/tc2.git",
                                "version": "feat/test",
                            },
                            "tc3": {
                                "url": "https://example.com/tc3.git",
                                "version": "master",
                            },
                        },
                        "customer_name": "${cluster:tenant}",
                    }
                }
            },
            0,
            ["No errors"],
        ),
        (
            {
                "test.yaml": {
                    "parameters": {
                        "components": {
                            "tc1": {
                                "url": "https://example.com/tc1.git",
                            },
                            "tc2": {
                                "url": "https://example.com/tc2.git",
                                "version": "feat/test",
                            },
                            "tc3": {
                                "url": "https://example.com/tc3.git",
                                "version": "master",
                            },
                        },
                        "customer_name": "${customer:name}",
                    }
                }
            },
            1,
            [
                "> Component specification for tc1 is missing key 'version' in {0}/test.yaml",
                "> Field 'parameters.customer_name' in file '{0}/test.yaml' "
                + "contains deprecated parameter '${{customer:name}}'",
                "Found 2 errors",
            ],
        ),
    ],
)
def test_inventory_lint_cli(
    tmp_path: Path,
    files: dict[str, dict[str, Any]],
    exitcode: int,
    stdout: list[str],
    cli_runner: RunnerFunc,
):
    for f, data in files.items():
        with open(tmp_path / f, "w") as fh:
            yaml.safe_dump(data, fh)

    result = cli_runner(["inventory", "lint", str(tmp_path)])

    assert result.exit_code == exitcode
    print(result.stdout)
    assert all(line.format(tmp_path) in result.stdout for line in stdout)


@pytest.mark.parametrize(
    "parameters,args",
    [
        ({}, []),
        ({"components": {"tc1": {"url": "https://example.com", "version": "v1"}}}, []),
        (
            {"components": {"tc1": {"url": "https://example.com", "version": "v1"}}},
            ["-o", "json"],
        ),
    ],
)
def test_component_versions_cli(
    cli_runner: RunnerFunc,
    tmp_path: Path,
    parameters: dict[str, Any],
    args: list[str],
):
    global_config = tmp_path / "global"
    global_config.mkdir()
    with open(global_config / "commodore.yml", "w") as f:
        yaml.safe_dump({"classes": ["global.test"]}, f)

    with open(global_config / "test.yml", "w") as f:
        yaml.safe_dump({"classes": ["foo.bar"], "parameters": parameters}, f)

    result = cli_runner(["inventory", "components", str(global_config)] + args)

    assert result.exit_code == 0
    if "json" in args:
        components = json.loads(result.stdout)
    else:
        components = yaml.safe_load(result.stdout)
    expected_components = parameters.get("components", {})
    assert components == expected_components


@pytest.mark.parametrize(
    "parameters,args",
    [
        ({}, []),
        ({"packages": {"tp1": {"url": "https://example.com", "version": "v1"}}}, []),
        (
            {"packages": {"tp1": {"url": "https://example.com", "version": "v1"}}},
            ["-o", "json"],
        ),
    ],
)
def test_package_versions_cli(
    cli_runner: RunnerFunc,
    tmp_path: Path,
    parameters: dict[str, Any],
    args: list[str],
):
    global_config = tmp_path / "global"
    global_config.mkdir()
    with open(global_config / "commodore.yml", "w") as f:
        yaml.safe_dump({"classes": ["global.test"]}, f)

    with open(global_config / "test.yml", "w") as f:
        yaml.safe_dump({"classes": ["foo.bar"], "parameters": parameters}, f)

    result = cli_runner(["inventory", "packages", str(global_config)] + args)

    assert result.exit_code == 0
    if "json" in args:
        pkgs = json.loads(result.stdout)
    else:
        pkgs = yaml.safe_load(result.stdout)
    expected_pkgs = parameters.get("packages", {})
    assert pkgs == expected_pkgs


@pytest.mark.parametrize(
    "parameters,args",
    [
        ({}, []),
        (
            {
                "components": {"tc1": {"url": "https://example.com", "version": "v1"}},
                "packages": {"tp1": {"url": "https://example.com", "version": "v1"}},
            },
            [],
        ),
        (
            {
                "components": {"tc1": {"url": "https://example.com", "version": "v1"}},
                "packages": {"tp1": {"url": "https://example.com", "version": "v1"}},
            },
            ["-o", "json"],
        ),
    ],
)
def test_show_inventory_cli(
    cli_runner: RunnerFunc,
    tmp_path: Path,
    parameters: dict[str, Any],
    args: list[str],
):
    global_config = tmp_path / "global"
    global_config.mkdir()
    with open(global_config / "commodore.yml", "w") as f:
        yaml.safe_dump({"classes": ["global.test"]}, f)

    with open(global_config / "test.yml", "w") as f:
        yaml.safe_dump({"classes": ["foo.bar"], "parameters": parameters}, f)

    result = cli_runner(["inventory", "show", str(global_config)] + args)

    assert result.exit_code == 0
    if "json" in args:
        inv = json.loads(result.stdout)
    else:
        inv = yaml.safe_load(result.stdout)
    expected_pkgs = parameters.get("packages", {})
    expected_components = parameters.get("components", {})
    assert inv.get("packages", {}) == expected_pkgs
    assert inv.get("components", {}) == expected_components
