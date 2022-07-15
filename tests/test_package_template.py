from __future__ import annotations
from pathlib import Path
from subprocess import call
from datetime import date

import json

import click
import pytest
import yaml

from commodore.config import Config
from commodore.gitrepo import GitRepo
from commodore.package.template import PackageTemplater

from conftest import RunnerFunc


def call_package_new(
    tmp_path: Path,
    cli_runner: RunnerFunc,
    package_name="test-package",
    golden="--no-golden-tests",
    output_dir: str = "",
    template_version: str = "",
    additional_test_cases: list[str] = [],
) -> str:
    atc_args = []
    for case in additional_test_cases:
        atc_args.extend(["-t", case])
    opt_args = []
    if output_dir:
        opt_args.append(output_dir)
    if template_version:
        opt_args.append(template_version)
    result = cli_runner(
        [
            "-d",
            tmp_path,
            "-vvv",
            "package",
            "new",
            package_name,
            golden,
        ]
        + opt_args
        + atc_args
    )
    assert result.exit_code == 0
    return result.stdout


@pytest.mark.parametrize("output_dir", ["", "--output-dir={0}"])
@pytest.mark.parametrize(
    "additional_test_cases",
    [
        [],
        ["foo"],
        ["foo", "bar"],
    ],
)
def test_run_package_new_command(
    tmp_path: Path,
    cli_runner: RunnerFunc,
    output_dir: str,
    additional_test_cases: list[str],
):
    output_dir = output_dir.format(tmp_path)

    call_package_new(
        tmp_path,
        cli_runner,
        output_dir=output_dir,
        additional_test_cases=additional_test_cases,
    )

    pkg_dir = tmp_path / "test-package"
    if output_dir == "":
        pkg_dir = tmp_path / "dependencies" / "pkg.test-package"

    expected_files = [
        Path(".editorconfig"),
        Path(".github", "ISSUE_TEMPLATE", "01_bug_report.md"),
        Path(".github", "ISSUE_TEMPLATE", "02_feature_request.md"),
        Path(".github", "ISSUE_TEMPLATE", "config.yml"),
        Path(".github", "PULL_REQUEST_TEMPLATE.md"),
        Path(".github", "changelog-configuration.json"),
        Path(".github", "workflows", "release.yaml"),
        Path(".github", "workflows", "test.yaml"),
        Path(".gitignore"),
        Path("Makefile"),
        Path("Makefile.vars.mk"),
        Path("README.md"),
        Path("docs", "antora.yml"),
        Path("docs", "modules", "ROOT", "pages", "index.adoc"),
        Path("renovate.json"),
        Path("tests", "defaults.yml"),
    ] + [Path("tests", f"{case}.yml") for case in additional_test_cases]

    assert pkg_dir.is_dir()
    for f in expected_files:
        assert (pkg_dir / f).is_file()

    with open(pkg_dir / ".github" / "workflows" / "test.yaml") as gh_test:
        workflows = yaml.safe_load(gh_test)
        instances = workflows["jobs"]["test"]["strategy"]["matrix"]["instance"]
        assert instances == list(["defaults"] + additional_test_cases)


@pytest.mark.parametrize(
    "slug,expected",
    [
        (
            "package-invalid",
            "The package slug may not start with 'package-'",
        ),
        ("00-invalid", "The package slug must match '^[a-z][a-z0-9-]+[a-z0-9]$'"),
        ("-invalid", "The package slug must match '^[a-z][a-z0-9-]+[a-z0-9]$'"),
        ("-invalid", "The package slug must match '^[a-z][a-z0-9-]+[a-z0-9]$'"),
        ("invalid-", "The package slug must match '^[a-z][a-z0-9-]+[a-z0-9]$'"),
        ("Invalid", "The package slug must match '^[a-z][a-z0-9-]+[a-z0-9]$'"),
        ("p_invalid", "The package slug must match '^[a-z][a-z0-9-]+[a-z0-9]$'"),
        ("t-invalid", "Package slug can't use reserved tenant prefix 't-'"),
        ("defaults", "Package can't use reserved slug 'defaults'"),
        ("components", "Package can't use reserved slug 'components'"),
        ("global", "Package can't use reserved slug 'global'"),
        ("params", "Package can't use reserved slug 'params'"),
    ],
)
def test_package_new_invalid_slug(config: Config, slug: str, expected: str):
    with pytest.raises(click.ClickException) as e:
        _ = PackageTemplater(config, slug)

    assert expected in str(e.value)


@pytest.mark.parametrize("golden", ["--golden-tests", "--no-golden-tests"])
@pytest.mark.parametrize("additional_test_cases", [[], ["foo"]])
def test_lint_package_template(
    tmp_path: Path,
    cli_runner: RunnerFunc,
    golden: str,
    additional_test_cases: list[str],
):
    call_package_new(
        tmp_path,
        cli_runner,
        golden=golden,
        output_dir=f"--output-dir={tmp_path}",
        additional_test_cases=additional_test_cases,
    )
    pkg_dir = tmp_path / "test-package"
    exit_status = call("make lint", shell=True, cwd=pkg_dir)
    assert exit_status == 0


@pytest.mark.parametrize(
    "initial_golden,update_golden,expected_golden",
    [
        ("--golden-tests", "--no-golden-tests", False),
        ("--no-golden-tests", "--golden-tests", True),
    ],
)
def test_package_update_golden(
    tmp_path: Path,
    cli_runner: RunnerFunc,
    initial_golden: str,
    update_golden: str,
    expected_golden: bool,
):
    call_package_new(
        tmp_path,
        cli_runner,
        golden=initial_golden,
        output_dir=f"--output-dir={tmp_path}",
    )
    pkg_dir = tmp_path / "test-package"

    cli_runner(["-d", tmp_path, "package", "update", update_golden, str(pkg_dir)])

    with open(pkg_dir / "renovate.json", "r", encoding="utf-8") as rjson:
        renovatejson = json.load(rjson)
        assert ("postUpgradeTasks" in renovatejson) == expected_golden
        assert ("suppressNotifications" in renovatejson) == expected_golden


def _verify_copyright_holder(pkg_dir: Path, holder="VSHN AG <info@vshn.ch>"):
    year = date.today().year
    with open(pkg_dir / "LICENSE", "r", encoding="utf-8") as lf:
        line = lf.readline()
        assert line == f"Copyright {year}, {holder}\n"


def test_package_update_copyright_holder(
    tmp_path: Path,
    cli_runner: RunnerFunc,
):
    call_package_new(
        tmp_path,
        cli_runner,
        output_dir=f"--output-dir={tmp_path}",
    )
    pkg_dir = tmp_path / "test-package"
    _verify_copyright_holder(pkg_dir)

    new_copyright = "Test Corp. <test@example.com>"
    cli_runner(
        [
            "-d",
            tmp_path,
            "package",
            "update",
            "--copyright",
            new_copyright,
            str(pkg_dir),
        ]
    )

    _verify_copyright_holder(pkg_dir, new_copyright)


@pytest.mark.parametrize(
    "initial_test_cases,additional_test_cases,remove_test_cases",
    (
        ([], ["foo"], []),
        (["foo"], ["bar"], ["foo"]),
        (["foo", "bar"], ["baz"], ["foo", "bar"]),
    ),
)
def test_package_update_test_cases(
    tmp_path: Path,
    cli_runner: RunnerFunc,
    initial_test_cases: list[str],
    additional_test_cases: list[str],
    remove_test_cases: list[str],
):
    # Create initial package
    call_package_new(
        tmp_path,
        cli_runner,
        golden="--golden-tests",
        additional_test_cases=initial_test_cases,
        output_dir=f"--output-dir={tmp_path}",
    )
    pkg_dir = tmp_path / "test-package"
    atc_args = []
    for case in additional_test_cases:
        atc_args.extend(["-t", case])
    dtc_args = []
    for case in remove_test_cases:
        dtc_args.extend(["--remove-test-case", case])

    cli_runner(
        ["-d", tmp_path, "package", "update", str(pkg_dir)] + atc_args + dtc_args
    )

    for case in set(initial_test_cases + additional_test_cases) - set(
        remove_test_cases
    ):
        assert (pkg_dir / "tests" / f"{case}.yml").is_file()

    for case in remove_test_cases:
        assert not (pkg_dir / "tests" / f"{case}.yml").exists()

    r = GitRepo(None, pkg_dir)
    assert not r.repo.is_dirty()
    assert len(r.repo.untracked_files) == 0
    assert r.repo.head.commit.message.startswith("Update from template\n\n")


def test_package_templater_from_existing_nonexistent(tmp_path: Path, config: Config):
    with pytest.raises(click.ClickException) as e:
        _ = PackageTemplater.from_existing(config, tmp_path / "test-package")

    assert str(e.value) == "Provided package path isn't a directory"
