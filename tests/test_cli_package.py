from __future__ import annotations

import os

from collections.abc import Iterable
from datetime import timedelta
from pathlib import Path
from typing import Type
from unittest import mock

import pytest
import yaml

from commodore.cli import package
from commodore.package import Package
from commodore.package.template import PackageTemplater

from conftest import RunnerFunc


@mock.patch.object(package, "sync_dependencies")
@pytest.mark.parametrize("ghtoken", [None, "ghp_fake-token"])
def test_package_sync_cli(
    mock_sync_packages, ghtoken, tmp_path: Path, cli_runner: RunnerFunc
):
    os.chdir(tmp_path)
    if ghtoken is not None:
        os.environ["COMMODORE_GITHUB_TOKEN"] = ghtoken

    pkg_list = tmp_path / "pkgs.yaml"
    with open(pkg_list, "w", encoding="utf-8") as f:
        yaml.safe_dump(["projectsyn/package-foo"], f)

    def sync_pkgs(
        config,
        pkglist: Path,
        dry_run: bool,
        pr_branch: str,
        pr_labels: Iterable[str],
        deptype: Type,
        templater: Type,
        pr_batch_size: int,
        github_pause: int,
    ):
        assert config.github_token == ghtoken
        assert pkglist.absolute() == pkg_list.absolute()
        assert not dry_run
        assert pr_branch == "template-sync"
        assert list(pr_labels) == []
        assert deptype == Package
        assert templater == PackageTemplater
        assert pr_batch_size == 10
        assert github_pause == timedelta(seconds=120)

    mock_sync_packages.side_effect = sync_pkgs
    result = cli_runner(["package", "sync", "pkgs.yaml"])
    print(result.stdout)
    assert result.exit_code == (1 if ghtoken is None else 0)
