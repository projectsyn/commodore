from pathlib import Path
from subprocess import call

import click
import pytest

from commodore.config import Config
from commodore.package.template import PackageTemplater


def call_package_new(
    tmp_path: Path,
    package_name="test-package",
    golden="--no-golden-tests",
    output_dir: str = "",
    template_version: str = "",
):
    exit_status = call(
        f"commodore -d {tmp_path} -vvv package new {package_name}"
        + f" {golden} {output_dir} {template_version}",
        shell=True,
    )
    assert exit_status == 0


@pytest.mark.parametrize("output_dir", ["", "--output-dir={0}"])
def test_run_package_new_command(tmp_path: Path, output_dir: str):
    output_dir = output_dir.format(tmp_path)

    call_package_new(tmp_path, output_dir=output_dir)

    pkg_dir = tmp_path / "test-package"
    if output_dir == "":
        pkg_dir = tmp_path / "inventory" / "classes" / "test-package"

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
    ]

    assert pkg_dir.is_dir()
    for f in expected_files:

        assert (pkg_dir / f).is_file()


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
def test_lint_package_template(tmp_path: Path, golden: str):
    call_package_new(tmp_path, golden=golden, output_dir=f"--output-dir={tmp_path}")
    pkg_dir = tmp_path / "test-package"
    exit_status = call("make lint", shell=True, cwd=pkg_dir)
    assert exit_status == 0
