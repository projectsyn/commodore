"""
Tests for command line interface (CLI)
"""
import os


def test_runas_module():
    """
    Can this package be run as a Python module?
    """
    exit_status = os.system('python -m commodore')
    assert exit_status == 0


def test_entrypoint():
    """
    Is entrypoint script installed?
    """
    exit_status = os.system('commodore --help')
    assert exit_status == 0


def test_clean_command():
    """
    Is subcommand available?
    """
    exit_status = os.system('commodore catalog clean --help')
    assert exit_status == 0


def test_compile_command():
    """
    Is subcommand available?
    """
    exit_status = os.system('commodore catalog compile --help')
    assert exit_status == 0


def test_component_new_command():
    """
    Is subcommand available?
    """
    exit_status = os.system('commodore component new --help')
    assert exit_status == 0


def test_component_compile_command():
    """
    Is subcommand available?
    """
    exit_status = os.system('commodore component compile --help')
    assert exit_status == 0
