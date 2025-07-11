import hashlib
import json
import os
import platform
import shutil
import subprocess  # nosec
from copy import deepcopy

from datetime import datetime
from pathlib import Path
from typing import Optional

import click
import github
import requests

from requests.exceptions import ConnectionError, HTTPError
from xdg.BaseDirectory import xdg_cache_home

from commodore.config import Config

REQUIRED_TOOLS = ["helm", "jb", "kustomize"]

_tool_version_arg = {
    "jb": ["--version"],
    "helm": ["version", "--template", "{{.Version}}"],
    "kustomize": ["version"],
}

TOOL_REPOS = {
    "jb": "projectsyn/jsonnet-bundler",
    "helm": "helm/helm",
    "kustomize": "kubernetes-sigs/kustomize",
}


MANAGED_TOOLS_PATH = Path(xdg_cache_home) / "commodore" / "tools"
MANAGED_TOOLS_STATE = MANAGED_TOOLS_PATH / "state.json"

TOOL_INSTALL_SCRIPT_URL = {
    "helm": "https://raw.githubusercontent.com/helm/helm/master/scripts/get-helm-3",
    "kustomize": "https://raw.githubusercontent.com/kubernetes-sigs/kustomize/master/hack/install_kustomize.sh",
}


class ToolInfo:
    tool: str
    path: Optional[str]
    version: Optional[str]

    def __init__(self, tool: str):
        if tool not in REQUIRED_TOOLS:
            raise ValueError(f"Unknown tool {tool}")

        self.tool = tool
        self.path = shutil.which(tool)
        self.version = None
        if self.path:
            self.version = (
                subprocess.run(
                    [self.path] + _tool_version_arg[tool],
                    stderr=subprocess.STDOUT,
                    stdout=subprocess.PIPE,
                )
                .stdout.decode("utf-8")
                .strip()
            )

    @property
    def available(self) -> bool:
        return self.path is not None

    def info(self) -> str:
        if not self.path:
            return "NOT FOUND IN PATH"
        return f"{self.path}, version: {self.version}"


def setup_path():
    path = os.environ["PATH"].split(os.pathsep)
    if MANAGED_TOOLS_PATH.as_posix() not in path:
        path = [MANAGED_TOOLS_PATH.as_posix()] + path

    os.environ["PATH"] = os.pathsep.join(path)


def load_state() -> dict[str, str]:
    state = {}
    if MANAGED_TOOLS_STATE.is_file():
        with open(MANAGED_TOOLS_STATE, "r", encoding="utf-8") as statef:
            state = json.load(statef)

    update = False
    for tool in REQUIRED_TOOLS:
        if tool not in state:
            continue
        tpath = shutil.which(tool)
        if tpath and Path(tpath).parent != MANAGED_TOOLS_PATH:
            click.secho(
                f"Tool {tool} missing in managed tools path, removing from state",
                fg="yellow",
            )
            del state[tool]
            update = True

    if update:
        with open(MANAGED_TOOLS_STATE, "w", encoding="utf-8") as statef:
            json.dump(state, statef)

    return state


def list_tools(config: Config, version_check: bool):
    tool_versions = {}
    if version_check:
        click.secho("Fetching latest tool versions from GitHub", fg="yellow")
        for tool in REQUIRED_TOOLS:
            tool_versions[tool] = latest_version(config, tool)

    for tool in REQUIRED_TOOLS:
        tinfo = ToolInfo(tool)
        if not tinfo.version:
            click.secho(f"{tool} missing!", fg="red")
            continue
        managed = tool in config.managed_tools
        updated = config.managed_tools.get(tool, "UNKNOWN")
        version = "N/A"
        versioncolor = None
        upgradetext = "Version check skipped"
        if tool in tool_versions:
            version = tool_versions[tool]
            if version.removeprefix("v") != tinfo.version.removeprefix("v"):
                # TODO(sg): what's the best color here?
                versioncolor = "yellow"
                upgradetext = "Upgrade available!"
            else:
                upgradetext = "No upgrade available"
        click.secho(f"{tool} {tinfo.version}", bold=True)
        click.echo(f"Location:       {tinfo.path}")
        click.echo(f"Managed:        {managed}")
        click.secho(
            f"Latest version: {version} ("
            + click.style(upgradetext, fg=versioncolor)
            + ")"
        )
        click.echo(f"Updated:        {updated}")


def latest_version(config: Config, tool: str) -> str:
    auth = None
    if config.github_token:
        auth = github.Auth.Token(config.github_token)
    elif config.verbose:
        click.secho(
            "[WARN] Using unauthenticated GitHub client, strict rate limits apply",
            fg="yellow",
        )
    gh = github.Github(auth=auth)
    try:
        gr = gh.get_repo(TOOL_REPOS[tool])
    except github.UnknownObjectException:
        raise click.ClickException(f"GitHub repo for tool {tool} not found")
    latest_release = gr.get_latest_release()
    return latest_release.tag_name.removeprefix(f"{tool}/")


def install_jb(config: Config, jb_version: str):
    machine = platform.machine()
    match machine:
        case "x86_64":
            arch = "amd64"
        case "aarch64":
            arch = "arm64"
        case a:
            arch = a
    system = platform.system().lower()
    click.echo(f" > Downloading jb {jb_version}")
    base_url = (
        f"https://github.com/projectsyn/jsonnet-bundler/releases/download/{jb_version}"
    )
    jb_file = f"jb_{system}_{arch}"
    jb_url = f"{base_url}/{jb_file}"
    jb_checksums_url = f"{base_url}/checksums.txt"
    jb_path = MANAGED_TOOLS_PATH / "jb"
    try:
        jb_chksums = requests.get(jb_checksums_url, timeout=config.request_timeout)
        jb_chksums.raise_for_status()
        jb_data = requests.get(jb_url, timeout=config.request_timeout)
        jb_data.raise_for_status()
    except (ConnectionError, HTTPError) as e:
        raise click.ClickException(f"Failed to download jb: {e}")
    click.echo(" > Validating checksum for jb")
    jb_content = jb_data.content
    jb_sha256 = hashlib.sha256(jb_content).hexdigest()
    checksums = [line.split("  ") for line in jb_chksums.text.strip().splitlines()]
    for sum, name in checksums:
        if name == jb_file:
            if sum != jb_sha256:
                raise click.ClickException(f"Failed to validate checksum for {jb_file}")
            else:
                break
    else:
        raise click.ClickException(f"No checksum available for {jb_file}")

    with open(jb_path, "wb") as jbf:
        jbf.write(jb_data.content)
    jb_path.chmod(0o755)


def install_script(config: Config, tool: str, version: Optional[str]):
    if version and version.startswith("v"):
        # this command expects that an optional v prefix for the version has been
        # stripped.
        raise ValueError(
            "Function install_script() expects parameter `version` to not be prefixed with 'v'."
        )
    install_args = []
    if tool == "helm":
        if version:
            install_args = ["--version", f"v{version}"]
        install_args = install_args + ["--no-sudo"]
    elif tool == "kustomize":
        if version:
            install_args = [version]
        install_args = install_args + [MANAGED_TOOLS_PATH.as_posix()]
    install_script = TOOL_INSTALL_SCRIPT_URL[tool]
    try:
        script_data = requests.get(install_script, timeout=config.request_timeout)
        script_data.raise_for_status()
    except (ConnectionError, HTTPError) as e:
        raise click.ClickException(
            f"Failed to download install script for tool {tool}: {e}"
        )
    script = MANAGED_TOOLS_PATH / f"{tool}-install.sh"
    with open(script, "w", encoding="utf-8") as scriptf:
        scriptf.write(script_data.text)
    script.chmod(0o755)
    # create a copy of os.environ so we don't pollute our own env.
    env = deepcopy(os.environ)
    env["HELM_INSTALL_DIR"] = MANAGED_TOOLS_PATH.as_posix()
    if config.github_token:
        env["GITHUB_TOKEN"] = config.github_token
    try:
        result = subprocess.run([script.as_posix()] + install_args, env=env)
        result.check_returncode()
    except (PermissionError, subprocess.CalledProcessError) as e:
        raise click.ClickException(f"Failed to run install script for tool {tool}: {e}")
    script.unlink()


def do_install(config: Config, tool: str, version: Optional[str]):
    if version:
        version = version.removeprefix("v")
    if tool == "jb":
        if version:
            jb_version = f"v{version}"
        else:
            jb_version = latest_version(config, "jb")
        install_jb(config, jb_version)
    else:
        install_script(config, tool, version)

    state = load_state()
    now = datetime.now()
    state[tool] = now.isoformat(timespec="seconds")
    with open(MANAGED_TOOLS_STATE, "w", encoding="utf-8") as statef:
        json.dump(state, statef)


def check_known(tool: str):
    if tool not in REQUIRED_TOOLS:
        raise click.ClickException(
            f"Unknown tool {tool}. "
            + "Commodore currently supports managing the following tools: "
            + ", ".join(REQUIRED_TOOLS)
        )


def install_tool(config: Config, tool: str, version: Optional[str]):
    check_known(tool)
    if tool in config.managed_tools:
        click.echo(
            f"Tool {tool} already installed. "
            + f"Use `commodore tool upgrade {tool}` to upgrade installed tools."
        )
        return

    click.secho(f"Installing tool {tool}", bold=True)
    MANAGED_TOOLS_PATH.mkdir(parents=True, exist_ok=True)
    do_install(config, tool, version)


def install_missing_tools(config: Config):
    MANAGED_TOOLS_PATH.mkdir(parents=True, exist_ok=True)
    missing_tools = set(REQUIRED_TOOLS) - set(config.managed_tools.keys())
    if len(missing_tools) == 0:
        click.echo(
            "All required tools are already managed by Commodore.\n\n"
            + "Use `commodore tool upgrade --all` to upgrade all tools to their latest versions."
        )
        return

    for tool in sorted(REQUIRED_TOOLS):
        if tool in config.managed_tools:
            click.secho(f"Tool {tool} already managed, skipping...", fg="yellow")
            continue
        click.secho(f"Installing tool {tool}", bold=True)
        do_install(config, tool, None)


def do_upgrade(config: Config, tool: str, version: Optional[str]):
    # The kustomize install script is unhappy if the kustomize binary is already
    # present in the install directory. To keep it simple, we unlink the old
    # tool binary for all tools when doing an upgrade (note that this generates
    # some extra work for the Helm install script when calling tool upgrade when
    # no upgrade is available). Notably we only unlink the existing tool when
    # it's in our MANAGED_TOOLS_PATH, so we never unlink a manually installed
    # copy of a tool (e.g. in `~/.local/bin`)
    tool_path_str = shutil.which(tool)
    if tool_path_str:
        tool_path = Path(tool_path_str)
        if tool_path.parent == MANAGED_TOOLS_PATH:
            tool_path.unlink()
    do_install(config, tool, version)


def upgrade_tool(config: Config, tool: str, version: Optional[str]):
    check_known(tool)
    if tool not in config.managed_tools:
        click.echo(
            f"Tool {tool} not installed yet. "
            + f"Use `commodore tool install {tool}` to install tools."
        )
        return

    do_upgrade(config, tool, version)


def upgrade_all_tools(config: Config):
    if len(config.managed_tools) == 0:
        click.echo(
            "No tools managed by Commodore yet.\n\n"
            + "Use `commodore tool install --missing` to install the latest version for all required tools."
        )
        return

    for tool in sorted(REQUIRED_TOOLS):
        if tool not in config.managed_tools:
            click.secho(f"Tool {tool} not managed, skipping...", fg="yellow")
            continue
        click.secho(f"Upgrading tool {tool}", bold=True)
        do_upgrade(config, tool, None)
