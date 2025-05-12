"""
Tests for command line interface (CLI)
"""

from subprocess import call


def test_runas_module():
    """
    Can this package be run as a Python module?
    """
    exit_status = call("python -m commodore", shell=True)
    # click 8.2 changed exit code for `no_args_is_help` from 0 to 2
    assert exit_status == 2


def test_entrypoint():
    """
    Is entrypoint script installed?
    """
    exit_status = call("commodore --help", shell=True)
    assert exit_status == 0


def test_clean_command():
    """
    Is subcommand available?
    """
    exit_status = call("commodore catalog clean --help", shell=True)
    assert exit_status == 0


def test_compile_command():
    """
    Is subcommand available?
    """
    exit_status = call("commodore catalog compile --help", shell=True)
    assert exit_status == 0


def test_component_new_command():
    """
    Is subcommand available?
    """
    exit_status = call("commodore component new --help", shell=True)
    assert exit_status == 0


def test_component_compile_command():
    """
    Is subcommand available?
    """
    exit_status = call("commodore component compile --help", shell=True)
    assert exit_status == 0


def test_inventory_show_command():
    exit_status = call("commodore inventory show --help", shell=True)
    assert exit_status == 0


def test_inventory_components_command():
    exit_status = call("commodore inventory components --help", shell=True)
    assert exit_status == 0


def test_inventory_packages_command():
    exit_status = call("commodore inventory packages --help", shell=True)
    assert exit_status == 0


def test_inventory_lint_command():
    exit_status = call("commodore inventory lint --help", shell=True)
    assert exit_status == 0


def test_login_command():
    exit_status = call("commodore login --help", shell=True)
    assert exit_status == 0


def test_fetch_token_command():
    exit_status = call("commodore fetch-token --help", shell=True)
    assert exit_status == 0


def test_package_compile_command():
    exit_status = call("commodore package compile --help", shell=True)
    assert exit_status == 0


def test_package_new_command():
    exit_status = call("commodore package new --help", shell=True)
    assert exit_status == 0


def test_package_update_command():
    exit_status = call("commodore package update --help", shell=True)
    assert exit_status == 0


def test_package_sync_command():
    exit_status = call("commodore package sync --help", shell=True)
    assert exit_status == 0
