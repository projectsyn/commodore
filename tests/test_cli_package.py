from __future__ import annotations

import os

from collections.abc import Iterable
from datetime import timedelta
from pathlib import Path
from typing import Optional, Type
from unittest import mock

import pytest
import yaml

from commodore.cli import package
from commodore.package import Package
from commodore.package.template import PackageTemplater

from conftest import RunnerFunc, make_mock_templater


@pytest.mark.parametrize("template_version", [None, "main^"])
@mock.patch.object(package, "PackageTemplater")
def test_update_package_cli(mock_templater, tmp_path, cli_runner, template_version):
    ppath = tmp_path / "test-package"
    ppath.mkdir()

    mt = make_mock_templater(mock_templater, ppath)

    template_arg = (
        [f"--template-version={template_version}"]
        if template_version is not None
        else []
    )

    result = cli_runner(["package", "update", str(ppath)] + template_arg)

    assert result.exit_code == 0
    assert mt.template_version == template_version


@mock.patch.object(package, "sync_dependencies")
@pytest.mark.parametrize(
    "ghtoken,template_version",
    [
        (None, None),
        ("ghp_fake-token", None),
        ("ghp_fake-token", "custom-template-version"),
    ],
)
def test_package_sync_cli(
    mock_sync_packages,
    ghtoken,
    template_version,
    tmp_path: Path,
    cli_runner: RunnerFunc,
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
        filter: str,
        tmpl_version: Optional[str],
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
        assert filter == ""
        assert tmpl_version == template_version

    mock_sync_packages.side_effect = sync_pkgs
    template_version_flag = (
        [f"--template-version={template_version}"]
        if template_version is not None
        else []
    )
    result = cli_runner(["package", "sync", "pkgs.yaml"] + template_version_flag)
    print(result.stdout)
    assert result.exit_code == (1 if ghtoken is None else 0)
