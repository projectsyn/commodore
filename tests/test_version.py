import sys

import pytest

from unittest.mock import patch
from importlib.metadata import version as pyversion

from conftest import RunnerFunc

from commodore import version


def test_version_cli(cli_runner: RunnerFunc):
    result = cli_runner(["version"])
    # NOTE(sg): exit code is 0 if all external tools are available
    assert result.exit_code == 0
    assert result.output.startswith("Commodore ")
    assert "Core dependency versions" in result.output
    assert f"kapitan: {pyversion('kapitan')}" in result.output
    assert f"gojsonnet: {pyversion('gojsonnet')}" in result.output
    assert f"reclass-rs: {pyversion('reclass-rs')}" in result.output
    assert "External tool versions" in result.output
    assert "helm: " in result.output
    assert "jb: " in result.output
    assert "kustomize: " in result.output


def test_version_cli_missing_external(cli_runner: RunnerFunc, fs):
    # allow access to the real Python prefix (system or virtualenv)
    fs.add_real_directory(sys.prefix)
    result = cli_runner(["version"])
    assert "helm: NOT FOUND IN PATH" in result.output
    assert "jb: NOT FOUND IN PATH" in result.output
    assert "kustomize: NOT FOUND IN PATH" in result.output
    # NOTE(sg): exit code is 127 if external tools are missing. We use pyfakefs
    # to hide the host fs except for the Python prefix.
    assert result.exit_code == 127


def test_version_native_find_so_non_native():
    with pytest.raises(ValueError) as exc:
        version._native_find_so("kapitan")
    assert "Unable to parse build info for kapitan: no unique *.so found" in str(exc)


def test_version_gojsonnet_buildinfo_no_unique_so():
    def mock_find_so(_dep):
        raise ValueError("Mock Error")

    with patch.object(version, "_native_find_so") as native_find_so_mock:
        native_find_so_mock.side_effect = mock_find_so
        build_info = version._buildinfo["gojsonnet"]()
        assert build_info == "Mock Error"
