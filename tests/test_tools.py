import hashlib
import json
import os
import textwrap
import stat
import sys

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from unittest.mock import patch, MagicMock

import click
import pytest
import responses

from commodore.config import Config

from commodore import tools

from test_dependency_sync import API_TOKEN_MATCHER

DATA_DIR = Path(__file__).parent.absolute() / "testdata" / "github"

TOOL_VERSIONS = {
    "helm": "v3.18.3",
    "jb": "0.6.3",
    "kustomize": "v5.7.0",
}


class MockToolInfo:
    tool: str
    path: Optional[str]
    version: Optional[str]

    def __init__(self, tool: str):
        self.tool = tool
        self.path = f"/path/to/{tool}"
        self.version = TOOL_VERSIONS[tool]


def _parse_list_tools_output(out: str) -> dict[str, list[str]]:
    tool = None
    tool_lines = {}
    for line in out.splitlines():
        trimmed_line = " ".join(line.strip().split())
        if trimmed_line.startswith(tuple(TOOL_VERSIONS.keys())):
            tool = trimmed_line.split(" ")[0]
        tool_lines.setdefault(tool, []).append(trimmed_line)
    return tool_lines


def _setup_tool_github_responses(
    auth=False, bad_jb_checksums=False, missing_jb_checksums=False
) -> dict[str, str]:
    latest_versions = {}
    matchers = []
    if auth:
        matchers = [API_TOKEN_MATCHER]
    for repo, tool in {
        "helm/helm": "helm",
        "projectsyn/jsonnet-bundler": "jb",
        "kubernetes-sigs/kustomize": "kustomize",
    }.items():
        repo_key = repo.replace("/", "-")
        with open(DATA_DIR / f"{repo_key}.json", "r", encoding="utf-8") as respf:
            resp = json.load(respf)
            responses.add(
                responses.GET,
                f"https://api.github.com:443/repos/{repo}",
                json=resp,
                status=200,
                match=matchers,
            )
        with open(
            DATA_DIR / f"{repo_key}-releases-latest.json", "r", encoding="utf-8"
        ) as latestf:
            latest = json.load(latestf)
            responses.add(
                responses.GET,
                f"https://api.github.com:443/repos/{repo}/releases/latest",
                json=latest,
                status=200,
                match=matchers,
            )
            latest_versions[tool] = latest["tag_name"].removeprefix(f"{tool}/")

    jb_variants = [
        "jb_darwin_amd64",
        "jb_darwin_arm64",
        "jb_linux_amd64",
        "jb_linux_arm64",
    ]
    jb_data = [f"#!/bin/sh\necho 'FAKE JB: {variant}'\n" for variant in jb_variants]
    if missing_jb_checksums:
        jb_checksums = "\n"
    else:
        if bad_jb_checksums:
            fake_chksums = [
                hashlib.sha256(variant.replace("FAKE ", "").encode("utf-8")).hexdigest()
                for variant in jb_data
            ]
        else:
            fake_chksums = [
                hashlib.sha256(variant.encode("utf-8")).hexdigest()
                for variant in jb_data
            ]
        jb_checksums = "\n".join(
            [
                f"{chksum}  {variant}"
                for (variant, chksum) in zip(jb_variants, fake_chksums)
            ]
        )
    responses.add(
        responses.GET,
        "https://github.com/projectsyn/jsonnet-bundler/releases/download/v0.6.3/checksums.txt",
        body=jb_checksums,
        status=200,
    )
    for variant, data in zip(jb_variants, jb_data):
        responses.add(
            responses.GET,
            f"https://github.com/projectsyn/jsonnet-bundler/releases/download/v0.6.3/{variant}",
            body=data,
            status=200,
        )

    return latest_versions


def test_toolinfo_unknown():
    with pytest.raises(ValueError) as e:
        tools.ToolInfo("foo")
    assert "Unknown tool foo" in str(e)


@pytest.mark.skipif(
    sys.version_info < (3, 11),
    reason="pyfakefs doesn't work nicely with existing pathlib.Path objects on Python < 3.11",
)
def test_load_state(fs):
    state = {
        "helm": "2025-07-09T15:20:00",
        "jb": "2025-07-08T19:20:00",
        "kustomize": "2025-07-09T15:22:00",
    }
    fs.create_file(tools.MANAGED_TOOLS_STATE)
    fs.create_file(tools.MANAGED_TOOLS_PATH / "helm")
    fs.create_file(tools.MANAGED_TOOLS_PATH / "jb")
    kustomize = Path("/usr/local/bin/kustomize")
    fs.create_file(kustomize)
    kustomize.chmod(0o755)

    with open(tools.MANAGED_TOOLS_STATE, "w", encoding="utf-8") as statef:
        json.dump(state, statef)

    loaded_state = tools.load_state()
    del state["kustomize"]
    assert loaded_state == state


@patch.object(tools, "ToolInfo")
def test_list_tools_no_version_check(mock_tinfo, config: Config, capsys):
    mock_tinfo.side_effect = MockToolInfo
    tools.list_tools(config, False)

    out, _ = capsys.readouterr()
    tool_lines = _parse_list_tools_output(out)

    for tool, version in TOOL_VERSIONS.items():
        assert tool_lines[tool][0] == f"{tool} {version}"
        assert tool_lines[tool][1] == f"Location: /path/to/{tool}"
        assert tool_lines[tool][2] == f"Managed: {False}"
        assert tool_lines[tool][3] == "Latest version: N/A (Version check skipped)"
        assert tool_lines[tool][4] == "Updated: UNKNOWN"


@patch.object(tools, "ToolInfo")
@responses.activate
def test_list_tool_version_check_verbose(mock_tinfo, config: Config, capsys):
    config.update_verbosity(1)
    mock_tinfo.side_effect = MockToolInfo
    latest_versions = _setup_tool_github_responses()

    tools.list_tools(config, True)

    out, _ = capsys.readouterr()
    tool_lines = _parse_list_tools_output(out)

    for tool, version in TOOL_VERSIONS.items():
        assert tool_lines[tool][0] == f"{tool} {version}"
        assert tool_lines[tool][1] == f"Location: /path/to/{tool}"
        assert tool_lines[tool][2] == f"Managed: {False}"
        if latest_versions[tool].removeprefix("v") == TOOL_VERSIONS[tool].removeprefix(
            "v"
        ):
            # Latest version is always GH tag name even for tools that report
            # their own version without a v prefix.
            assert (
                tool_lines[tool][3]
                == f"Latest version: v{TOOL_VERSIONS[tool].removeprefix('v')} (No upgrade available)"
            )
        else:
            assert (
                tool_lines[tool][3]
                == f"Latest version: {latest_versions[tool]} (Upgrade available!)"
            )
        assert tool_lines[tool][4] == "Updated: UNKNOWN"


@patch.object(tools, "ToolInfo")
def test_list_tool_missing(mock_tinfo, config: Config, capsys):
    class MockToolInfo2(MockToolInfo):
        def __init__(self, tool):
            if tool != "jb":
                super().__init__(tool)
            else:
                self.tool = tool
                self.path = None
                self.version = None

    mock_tinfo.side_effect = MockToolInfo2

    tools.list_tools(config, False)

    out, _ = capsys.readouterr()
    tool_lines = _parse_list_tools_output(out)
    for tool, version in TOOL_VERSIONS.items():
        if tool == "jb":
            assert len(tool_lines[tool]) == 1
            assert tool_lines[tool][0] == f"{tool} missing!"
        else:
            assert len(tool_lines[tool]) == 5
            assert tool_lines[tool][0] == f"{tool} {version}"


@responses.activate
def test_latest_version_authenticated(config: Config):
    config.github_token = "ghp_fake-token"
    _setup_tool_github_responses(auth=True)

    jb_latest = tools.latest_version(config, "jb")
    assert jb_latest == "v0.6.3"


def test_check_known_unknown():
    with pytest.raises(click.ClickException) as e:
        tools.check_known("foo")
    assert e.value.message == (
        "Unknown tool foo. "
        + "Commodore currently supports managing the following tools: "
        + ", ".join(tools.REQUIRED_TOOLS)
    )


def test_install_tool_already_installed(config: Config, capsys):
    config.managed_tools = {"jb": "2025-07-09T15:22:00"}
    tools.install_tool(config, "jb", None)
    out, _ = capsys.readouterr()
    assert (
        out
        == "Tool jb already installed. Use `commodore tool upgrade jb` to upgrade installed tools.\n"
    )


@pytest.mark.skipif(
    sys.version_info < (3, 11),
    reason="pyfakefs doesn't work nicely with existing pathlib.Path objects on Python < 3.11",
)
@responses.activate
def test_install_jb(config: Config, fs, capsys):
    fs.add_real_directory(os.curdir)
    fs.add_real_directory(DATA_DIR)

    config.managed_tools = {}
    _setup_tool_github_responses()
    assert not tools.MANAGED_TOOLS_PATH.exists()

    tools.install_tool(config, "jb", None)

    out, _ = capsys.readouterr()
    outlines = [line.strip() for line in out.splitlines()]

    assert len(outlines) == 3
    assert outlines[0] == "Installing tool jb"
    assert outlines[1] == "> Downloading jb v0.6.3"
    assert outlines[2] == "> Validating checksum for jb"

    jb_path = tools.MANAGED_TOOLS_PATH / "jb"
    assert jb_path.is_file()

    jb_mode = jb_path.stat().st_mode
    assert stat.S_ISREG(jb_mode)
    assert stat.S_IMODE(jb_mode) == 0o755

    with open(tools.MANAGED_TOOLS_STATE, "r", encoding="utf-8") as statef:
        state = json.load(statef)
    assert len(state) == 1
    assert "jb" in state
    updated = datetime.fromisoformat(state["jb"])
    assert datetime.now() - updated < timedelta(seconds=1)


@pytest.mark.skipif(
    sys.version_info < (3, 11),
    reason="pyfakefs doesn't work nicely with existing pathlib.Path objects on Python < 3.11",
)
@responses.activate
@patch.object(tools.platform, "machine")
@patch.object(tools.platform, "system")
@pytest.mark.parametrize(
    "machine,system",
    [
        ("x86_64", "Linux"),
        ("amd64", "Linux"),
        ("aarch64", "Linux"),
        ("x86_64", "Darwin"),
        ("arm64", "Darwin"),
    ],
)
def test_install_jb_arch(
    mock_system: MagicMock,
    mock_machine: MagicMock,
    config: Config,
    fs,
    capsys,
    machine: str,
    system: str,
):
    mock_machine.return_value = machine
    mock_system.return_value = system
    fs.add_real_directory(os.curdir)
    fs.add_real_directory(DATA_DIR)

    config.managed_tools = {}
    _setup_tool_github_responses()
    assert not tools.MANAGED_TOOLS_PATH.exists()

    tools.install_tool(config, "jb", None)

    osname = system.lower()
    match machine:
        case "aarch64":
            arch = "arm64"
        case "x86_64":
            arch = "amd64"
        case m:
            arch = m
    jb_binary = f"jb_{osname}_{arch}"

    with open(tools.MANAGED_TOOLS_PATH / "jb", "r", encoding="utf-8") as jbf:
        jb_text = jbf.read()
        assert f"FAKE JB: {jb_binary}" in jb_text


@pytest.mark.skipif(
    sys.version_info < (3, 11),
    reason="pyfakefs doesn't work nicely with existing pathlib.Path objects on Python < 3.11",
)
@responses.activate
def test_install_jb_bad_checksum(config: Config, capsys, fs):
    fs.add_real_directory(os.curdir)
    fs.add_real_directory(DATA_DIR)

    config.managed_tools = {}
    _setup_tool_github_responses(bad_jb_checksums=True)
    assert not tools.MANAGED_TOOLS_PATH.exists()
    with pytest.raises(click.ClickException) as exc:
        tools.install_tool(config, "jb", "v0.6.3")

    assert str(exc.value).startswith("Failed to validate checksum for jb_")


@pytest.mark.skipif(
    sys.version_info < (3, 11),
    reason="pyfakefs doesn't work nicely with existing pathlib.Path objects on Python < 3.11",
)
@responses.activate
def test_install_jb_missing_checksum(config: Config, capsys, fs):
    fs.add_real_directory(os.curdir)
    fs.add_real_directory(DATA_DIR)

    config.managed_tools = {}
    _setup_tool_github_responses(missing_jb_checksums=True)
    assert not tools.MANAGED_TOOLS_PATH.exists()
    with pytest.raises(click.ClickException) as exc:
        tools.install_tool(config, "jb", "v0.6.3")

    assert str(exc.value).startswith("No checksum available for jb_")


@responses.activate
@pytest.mark.parametrize("github_token", ["", "ghp_fake-token"])
def test_install_helm(config: Config, capfd, tmp_path, github_token):
    # NOTE(sg): We use `capfd` for this test so we capture writes to
    # stdout/stderr (fd 1/2) from subprocesses.
    config.github_token = github_token

    responses.add(
        responses.GET,
        "https://raw.githubusercontent.com/helm/helm/master/scripts/get-helm-3",
        body=textwrap.dedent(
            """#!/bin/sh
        echo 'Helm installer'
        echo "command line=$@"
        echo "HELM_INSTALL_DIR=${HELM_INSTALL_DIR}"
        echo "GITHUB_TOKEN=${GITHUB_TOKEN}"
        """
        ),
        status=200,
    )

    with patch.object(tools, "MANAGED_TOOLS_PATH", new=tmp_path) as _:
        with patch.object(
            tools, "MANAGED_TOOLS_STATE", new=tmp_path / "state.json"
        ) as _:
            tools.install_tool(config, "helm", TOOL_VERSIONS["helm"])

    out, _ = capfd.readouterr()
    outlines = list(map(str.strip, out.splitlines()))
    assert len(outlines) == 5
    assert outlines[1] == "Helm installer"
    assert outlines[2] == f"command line=--version {TOOL_VERSIONS['helm']} --no-sudo"
    assert outlines[3] == f"HELM_INSTALL_DIR={tmp_path}"
    assert outlines[4] == f"GITHUB_TOKEN={github_token}"


@responses.activate
@pytest.mark.parametrize("github_token", ["", "ghp_fake-token"])
def test_install_kustomize(config: Config, capfd, tmp_path, github_token):
    # NOTE(sg): We use `capfd` for this test so we capture writes to
    # stdout/stderr (fd 1/2) from subprocesses.
    config.github_token = github_token

    responses.add(
        responses.GET,
        "https://raw.githubusercontent.com/kubernetes-sigs/kustomize/master/hack/install_kustomize.sh",
        body=textwrap.dedent(
            """#!/bin/sh
        echo 'Kustomize installer'
        echo "command line=$@"
        echo "HELM_INSTALL_DIR=${HELM_INSTALL_DIR}"
        echo "GITHUB_TOKEN=${GITHUB_TOKEN}"
        """
        ),
        status=200,
    )

    with patch.object(tools, "MANAGED_TOOLS_PATH", new=tmp_path) as _:
        with patch.object(
            tools, "MANAGED_TOOLS_STATE", new=tmp_path / "state.json"
        ) as _:
            tools.install_tool(config, "kustomize", TOOL_VERSIONS["kustomize"])

    out, _ = capfd.readouterr()
    outlines = list(map(str.strip, out.splitlines()))
    assert len(outlines) == 5
    assert outlines[1] == "Kustomize installer"
    assert (
        outlines[2]
        == f"command line={TOOL_VERSIONS['kustomize'].removeprefix('v')} {tmp_path}"
    )
    # we inject the HELM_INSTALL_DIR and GITHUB_TOKEN env vars regardless of
    # which tool we install.
    assert outlines[3] == f"HELM_INSTALL_DIR={tmp_path}"
    assert outlines[4] == f"GITHUB_TOKEN={github_token}"


@patch.object(tools, "do_install")
@pytest.mark.parametrize(
    "managed,output",
    [
        (
            {
                "helm": "2025-07-11T11:04:40",
                "jb": "2025-07-11T10:58:11",
                "kustomize": "2025-07-11T11:05:05",
            },
            "All required tools are already managed by Commodore.\n\n"
            + "Use `commodore tool upgrade --all` to upgrade all tools "
            + "to their latest versions.\n",
        ),
        (
            {"jb": "2025-07-11T10:58:11"},
            "Installing tool helm\n"
            + "Tool jb already managed, skipping...\n"
            + "Installing tool kustomize\n",
        ),
    ],
)
def test_install_missing_tools(
    mock_do_install: MagicMock,
    config: Config,
    capsys,
    managed: dict[str, str],
    output: str,
):
    config.managed_tools = managed

    tools.install_missing_tools(config)

    assert mock_do_install.call_count == len(tools.REQUIRED_TOOLS) - len(managed)

    out, _ = capsys.readouterr()
    assert out == output


def test_install_script_invalid_version(config: Config):
    with pytest.raises(ValueError) as exc:
        tools.install_script(config, "jb", "v0.6.3")

    assert (
        str(exc.value)
        == "Function install_script() expects parameter `version` to not be prefixed with 'v'."
    )


def test_upgrade_tool_not_installed(config: Config, capsys):
    config.managed_tools = {}
    tools.upgrade_tool(config, "jb", None)
    out, _ = capsys.readouterr()
    assert (
        out
        == "Tool jb not installed yet. Use `commodore tool install jb` to install tools.\n"
    )


@pytest.mark.skipif(
    sys.version_info < (3, 11),
    reason="pyfakefs doesn't work nicely with existing pathlib.Path objects on Python < 3.11",
)
@patch.object(tools, "do_install")
@pytest.mark.parametrize("managed_jb", [True, False])
def test_upgrade_tool(mock_do_install, config: Config, tmp_path, managed_jb):
    config.managed_tools["jb"] = "2025-07-10T12:00:00"
    if managed_jb:
        jb_file = tmp_path / "tools" / "jb"
    else:
        jb_file = tmp_path / "jb"
    jb_file.parent.mkdir(exist_ok=True)
    jb_file.touch()
    jb_file.chmod(0o755)

    def do_inst(_config: Config, tool: str, version: Optional[str]):
        assert tool == "jb"
        assert version is None

    mock_do_install.side_effect = do_inst

    # patching MANAGED_TOOLS_PATH for this test because comparing a pyfakefs
    # Path with a non-fake Path (the check whether we need to unlink an existing
    # managed tool) returns False for the same absolute path.
    with patch.object(tools, "MANAGED_TOOLS_PATH", new=tmp_path / "tools"):
        with patch.dict(
            os.environ, {"PATH": f"{tmp_path/'tools'}{os.pathsep}{tmp_path}"}
        ):
            tools.upgrade_tool(config, "jb", None)

    assert jb_file.exists() != managed_jb


@patch.object(tools, "do_upgrade")
@pytest.mark.parametrize(
    "managed,output",
    [
        (
            {},
            "No tools managed by Commodore yet.\n\n"
            + "Use `commodore tool install --missing` to install the latest "
            + "version for all required tools.\n",
        ),
        (
            {"jb": "2025-07-11T10:58:11"},
            "Tool helm not managed, skipping...\n"
            + "Upgrading tool jb\n"
            + "Tool kustomize not managed, skipping...\n",
        ),
    ],
)
def test_upgrade_all_tools(
    mock_do_upgrade: MagicMock,
    config: Config,
    capsys,
    managed: dict[str, str],
    output: str,
):
    config.managed_tools = managed

    tools.upgrade_all_tools(config)

    assert mock_do_upgrade.call_count == len(managed)

    out, _ = capsys.readouterr()
    assert out == output
