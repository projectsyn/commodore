"""Extended Commodore version information"""

import os
import sys

from importlib import metadata

import click
import reclass_rs

from commodore import tools
from commodore.config import Config

from pygobuildinfo import get_go_build_info


def _native_find_so(dep) -> os.PathLike[str]:
    files = metadata.files(dep)
    if not files:
        raise ValueError(
            f"Unable to parse build info for {dep}: no package files found"
        )
    so_files = [p.locate() for p in files if p.name.endswith(".so")]
    if len(so_files) != 1:
        raise ValueError(f"Unable to parse build info for {dep}: no unique *.so found")
    return so_files[0]


def _gojsonnet_buildinfo():
    try:
        so_file = _native_find_so("gojsonnet")
    except ValueError as e:
        return str(e)
    gobuildinfo = get_go_build_info(str(so_file))
    return f"Go compiler: {gobuildinfo['GoVersion']}"


def _reclass_rs_buildinfo():
    if hasattr(reclass_rs, "buildinfo"):
        buildinfo = reclass_rs.buildinfo()
        return f"Rust compiler: {buildinfo['rustc_version']}"
    # For reclass_rs 0.8.0 and older, we just return an informational message
    return "Parsing build info not supported for reclass-rs <= 0.8.0"


_buildinfo = {
    "gojsonnet": _gojsonnet_buildinfo,
    "reclass-rs": _reclass_rs_buildinfo,
    "kapitan": lambda: "",
}


def version_info(config: Config, version: str):
    exit_code = 0
    click.secho(f"Commodore {version}", bold=True)
    click.echo("")
    click.secho("Core dependency versions", bold=True)
    for dep in ["kapitan", "gojsonnet", "reclass-rs"]:
        dep_ver = metadata.version(dep)
        dep_buildinfo = _buildinfo[dep]()
        if dep_buildinfo:
            dep_buildinfo = f", build info: {dep_buildinfo}"
        click.echo(f"{dep}: {dep_ver}{dep_buildinfo}")
    click.echo("")
    click.secho("External tool versions", bold=True)
    for tool in tools.REQUIRED_TOOLS:
        tool_info = tools.ToolInfo(tool)
        fgcolor = None
        bold = False
        if not tool_info.available:
            fgcolor = "red"
            bold = True
            exit_code = 127
        click.secho(f"{tool}: {tool_info.info()}", fg=fgcolor, bold=bold)
    sys.exit(exit_code)
