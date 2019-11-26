"""
Tests for command line interface (CLI)
"""
import os
import pytest

import commodore.cli


def test_runas_module():
    """
    Can this package be run as a Python module?
    """
    exit_status = os.system('python -m commodore')
    assert exit_status == 0


def test_entrypoint():
    """
    Is entrypoint script installed? (setup.py)
    """
    exit_status = os.system('commodore --help')
    assert exit_status == 0


def test_clean_command():
    """
    Is subcommand available?
    """
    exit_status = os.system('commodore clean --help')
    assert exit_status == 0


def test_compile_command():
    """
    Is subcommand available?
    """
    exit_status = os.system('commodore compile --help')
    assert exit_status == 0


def test_newcomponent_command():
    """
    Is subcommand available?
    """
    exit_status = os.system('commodore new-component --help')
    assert exit_status == 0
