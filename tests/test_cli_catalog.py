from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest import mock

import pytest
import responses

from commodore.cli import catalog
from commodore.config import Config
from test_catalog import cluster_resp

from conftest import RunnerFunc


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
            "-oid",
        ]
    )
    print(result.stdout)

    assert result.exit_code == 0
    assert result.stdout.strip() == cluster_resp["id"]


def verify_config(expected: Config):
    def mock(cfg: Config, cluster: str):
        assert cfg.push == expected.push
        assert cfg.local == expected.local
        assert cfg.fetch_dependencies == expected.fetch_dependencies
        assert cfg.verbose == expected.verbose
        assert (
            cfg.tenant_repo_revision_override == expected.tenant_repo_revision_override
        )
        assert (
            cfg.global_repo_revision_override == expected.global_repo_revision_override
        )
        assert cluster == "c-cluster-id"

    return mock


def make_config(tmp_path: Path, expected: dict[str, Any]):
    config = Config(tmp_path)
    config.push = expected.get("push", False)
    config.local = expected.get("local", False)
    config.fetch_dependencies = expected.get("fetch_dependencies", True)
    config.update_verbosity(expected.get("verbose", 0))
    config.tenant_repo_revision_override = expected.get("tenant_rev")
    config.global_repo_revision_override = expected.get("global_rev")

    return config


@mock.patch.object(catalog, "login")
@mock.patch.object(catalog, "_compile")
@pytest.mark.parametrize(
    "args,expected,exitcode",
    [
        ([], {}, 0),
        (["--push"], {"push": True}, 0),
        (["--local"], {"local": True}, 0),
        # --no-fetch-dependencies has no effect unless `--local` is set.
        (["--no-fetch-dependencies"], {"fetch_dependencies": True}, 0),
        (
            ["--local", "--no-fetch-dependencies"],
            {"local": True, "fetch_dependencies": False},
            0,
        ),
        (["--global-repo-revision-override", "v1"], {"global_rev": "v1"}, 0),
        (["--tenant-repo-revision-override", "v1"], {"tenant_rev": "v1"}, 0),
        (
            [
                "--global-repo-revision-override",
                "v1",
                "--tenant-repo-revision-override",
                "v1",
            ],
            {"global_rev": "v1", "tenant_rev": "v1"},
            0,
        ),
        (
            ["--global-repo-revision-override", "v1", "--push"],
            {"global_rev": "v1", "push": False},
            1,
        ),
        (
            ["--tenant-repo-revision-override", "v1", "--push"],
            {"tenant_rev": "v1", "push": False},
            1,
        ),
        (["--api-url", "https://syn.example.com"], {"login": True}, 0),
        (
            ["--api-url", "https://syn.example.com", "--api-token", "token"],
            {"login": False},
            0,
        ),
        (["-v"], {"verbose": 1}, 0),
        (["-vvv"], {"verbose": 3}, 0),
        (["-v", "-v", "-v"], {"verbose": 3}, 0),
    ],
)
def test_catalog_compile_cli(
    mock_compile,
    mock_login,
    cli_runner: RunnerFunc,
    args: list[str],
    expected: dict[str, Any],
    exitcode: int,
    tmp_path: Path,
):
    mock_compile.side_effect = verify_config(make_config(tmp_path, expected))

    result = cli_runner(["catalog", "compile", "c-cluster-id"] + args)

    assert result.exit_code == exitcode
    if exitcode == 1:
        assert (
            "Cannot push changes when local global or tenant repo override is specified"
            in result.stdout
        )
    if "push" in expected and not expected.get("fetch_dependencies", True):
        assert (
            "--no-fetch-dependencies doesn't take effect unless --local is specified"
            in result.stdout
        )
    if expected.get("login", False):
        mock_login.assert_called()
