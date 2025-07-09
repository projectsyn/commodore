from unittest.mock import patch
from typing import Optional

import pytest

from conftest import RunnerFunc

from commodore.config import Config


@patch("commodore.tools.list_tools")
@patch("commodore.tools.load_state")
@pytest.mark.parametrize(
    "args,vcheck",
    [
        ([], True),
        (["--version-check"], True),
        (["--skip-version-check"], False),
        (["-V"], False),
    ],
)
def test_tool_list(
    mock_load_state,
    mock_list_tools,
    cli_runner: RunnerFunc,
    args: list[str],
    vcheck: bool,
):
    def mock_list(_config: Config, version_check: bool):
        assert version_check == vcheck

    mock_list_tools.side_effect = mock_list

    result = cli_runner(["tool", "list"] + args)
    assert result.exit_code == 0
    mock_load_state.assert_called_once()


@patch("commodore.tools.install_tool")
@patch("commodore.tools.load_state")
@pytest.mark.parametrize(
    "tool,args,expected_version",
    [
        ("jb", [], None),
        ("jb", ["--version", "v0.6.3"], "v0.6.3"),
    ],
)
def test_tool_install(
    mock_load_state,
    mock_install_tool,
    cli_runner: RunnerFunc,
    tool: str,
    args: list[str],
    expected_version,
):
    def mock_install(_config: Config, mtool: str, mversion: Optional[str]):
        assert mtool == tool
        assert mversion == expected_version

    mock_install_tool.side_effect = mock_install

    result = cli_runner(["tool", "install", tool] + args)
    assert result.exit_code == 0
    mock_load_state.assert_called_once()


@patch("commodore.tools.upgrade_tool")
@patch("commodore.tools.load_state")
@pytest.mark.parametrize(
    "tool,args,expected_version",
    [
        ("jb", [], None),
        ("jb", ["--version", "v0.6.3"], "v0.6.3"),
    ],
)
def test_tool_upgrade(
    mock_load_state,
    mock_upgrade_tool,
    cli_runner: RunnerFunc,
    tool: str,
    args: list[str],
    expected_version,
):
    def mock_upgrade(_config: Config, mtool: str, mversion: Optional[str]):
        assert mtool == tool
        assert mversion == expected_version

    mock_upgrade_tool.side_effect = mock_upgrade

    result = cli_runner(["tool", "upgrade", tool] + args)
    assert result.exit_code == 0
    mock_load_state.assert_called_once()
