from __future__ import annotations

import os

from collections.abc import Iterable
from datetime import timedelta
from pathlib import Path
from typing import Optional, Type
from unittest import mock

import pytest
import yaml

from commodore.component import Component
from commodore.component.template import ComponentTemplater

import commodore.cli.component as component

from conftest import RunnerFunc, make_mock_templater


@pytest.mark.parametrize("repo_dir", [False, True])
@mock.patch.object(component, "compile_component")
def test_compile_component_cli(mock_compile, tmp_path, repo_dir, cli_runner):
    cpath = tmp_path / "test-component"
    cpath.mkdir()

    def _compile(cfg, path, alias, values, search_paths, output, name):
        assert cfg.verbose == 0
        assert path == str(cpath)
        assert values == ()
        assert alias is None
        assert search_paths == ()
        assert output == "./"
        assert name == ""

    mock_compile.side_effect = _compile

    repo_dir_arg = []
    if repo_dir:
        repo_dir_arg = ["-r", str(tmp_path)]
    result = cli_runner(["component", "compile", str(cpath)] + repo_dir_arg)

    assert result.exit_code == 0

    if repo_dir:
        assert (
            result.stdout
            == " > Parameter `-r`/`--repo-directory` is deprecated and has no effect\n"
        )


@pytest.mark.parametrize("template_version", [None, "main^"])
@mock.patch.object(component, "ComponentTemplater")
def test_update_component_cli(mock_templater, tmp_path, cli_runner, template_version):
    cpath = tmp_path / "test-component"
    cpath.mkdir()

    mt = make_mock_templater(mock_templater, cpath)

    template_arg = (
        [f"--template-version={template_version}"]
        if template_version is not None
        else []
    )

    result = cli_runner(["component", "update", str(cpath)] + template_arg)

    assert result.exit_code == 0
    assert mt.template_version == template_version


@mock.patch.object(component, "sync_dependencies")
@pytest.mark.parametrize(
    "ghtoken,template_version",
    [
        (None, None),
        ("ghp_fake-token", None),
        ("ghp_fake-token", "custom-template-version"),
    ],
)
def test_component_sync_cli(
    mock_sync_dependencies,
    ghtoken,
    template_version,
    tmp_path: Path,
    cli_runner: RunnerFunc,
):
    os.chdir(tmp_path)
    if ghtoken is not None:
        os.environ["COMMODORE_GITHUB_TOKEN"] = ghtoken

    dep_list = tmp_path / "deps.yaml"
    with open(dep_list, "w", encoding="utf-8") as f:
        yaml.safe_dump(["projectsyn/component-foo"], f)

    def sync_deps(
        config,
        deplist: Path,
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
        assert deplist.absolute() == dep_list.absolute()
        assert not dry_run
        assert pr_branch == "template-sync"
        assert list(pr_labels) == []
        assert deptype == Component
        assert templater == ComponentTemplater
        assert pr_batch_size == 10
        assert github_pause == timedelta(seconds=120)
        assert filter == ""
        assert tmpl_version == template_version

    mock_sync_dependencies.side_effect = sync_deps
    template_version_flag = (
        [f"--template-version={template_version}"]
        if template_version is not None
        else []
    )
    result = cli_runner(["component", "sync", "deps.yaml"] + template_version_flag)
    assert result.exit_code == (1 if ghtoken is None else 0)
