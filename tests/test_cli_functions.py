from pathlib import Path
from typing import Any, Dict, List, Protocol
from unittest import mock

import pytest
import responses
import yaml

from click.testing import CliRunner, Result

from commodore import cli
from test_catalog import cluster_resp


class RunnerFunc(Protocol):
    def __call__(self, args: List[str]) -> Result:
        ...


@pytest.fixture
def cli_runner() -> RunnerFunc:
    r = CliRunner()
    return lambda args: r.invoke(cli.commodore, args)


@pytest.mark.parametrize(
    "args,exitcode,output",
    [
        (
            [],
            1,
            "Error: Can't fetch Lieutenant token. Please provide the Lieutenant API URL.\n",
        ),
        (
            ["--api-url=https://syn.example.com"],
            0,
            "id-1234\n",
        ),
    ],
)
@mock.patch.object(cli, "fetch_token")
def test_commodore_fetch_token(
    fetch_token,
    args: List[str],
    exitcode: int,
    output: str,
    cli_runner: RunnerFunc,
):
    fetch_token.side_effect = lambda cfg: "id-1234"

    result = cli_runner(["fetch-token"] + args)

    assert result.exit_code == exitcode
    assert result.stdout == output


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
                "> Component specification for tc1 is missing explict version in {0}/test.yaml",
                "> Field 'parameters.customer_name' in file '{0}/test.yaml' "
                + "contains deprecated parameter '${{customer:name}}'",
                "Found 2 errors",
            ],
        ),
    ],
)
def test_inventory_lint_cli(
    tmp_path: Path,
    files: Dict[str, Dict[str, Any]],
    exitcode: int,
    stdout: List[str],
    cli_runner: RunnerFunc,
):
    for f, data in files.items():
        with open(tmp_path / f, "w") as fh:
            yaml.safe_dump(data, fh)

    result = cli_runner(["inventory", "lint", str(tmp_path)])

    assert result.exit_code == exitcode
    assert all(line.format(tmp_path) in result.stdout for line in stdout)


@pytest.mark.parametrize(
    "parameters",
    [{}, {"components": {"tc1": {"url": "https://example.com", "version": "v1"}}}],
)
def test_component_versions_cli(
    cli_runner: RunnerFunc, tmp_path: Path, parameters: Dict[str, Any]
):
    global_config = tmp_path / "global"
    global_config.mkdir()
    with open(global_config / "commodore.yml", "w") as f:
        yaml.safe_dump({"classes": ["global.test"]}, f)

    with open(global_config / "test.yml", "w") as f:
        yaml.safe_dump({"parameters": parameters}, f)

    result = cli_runner(["inventory", "components", str(global_config)])

    assert result.exit_code == 0
    components = yaml.safe_load(result.stdout)
    expected_components = parameters.get("components", {})
    assert components == expected_components


@responses.activate
def test_catalog_list_cli(cli_runner: RunnerFunc):
    responses.add(
        responses.GET,
        "https://syn.example.com/clusters/",
        status=200,
        json=[cluster_resp],
    )

    result = cli_runner(
        [
            "catalog",
            "list",
            "--api-url",
            "https://syn.example.com",
            # Provide fake token to avoid having to mock the OIDC login for this test
            "--api-token",
            "token",
        ]
    )
    print(result.stdout)

    assert result.exit_code == 0
    assert result.stdout.strip() == cluster_resp["id"]
