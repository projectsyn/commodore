import pytest
import textwrap
from pathlib import Path as P

import click

from commodore.config import Config


@pytest.fixture
def config(tmp_path: P):
    return Config(
        tmp_path,
        api_url="https://syn.example.com",
        api_token="token",
    )


def test_verify_component_aliases(config):
    alias_data = {"baz": "bar"}
    config.register_component_aliases(alias_data)
    params = {"bar": {"multi_instance": True, "namespace": "syn-bar"}}

    config.verify_component_aliases(params)


def test_verify_component_aliases_error(config):
    alias_data = {"baz": "bar"}
    config.register_component_aliases(alias_data)
    params = {"bar": {"namespace": "syn-bar"}}

    with pytest.raises(click.ClickException):
        config.verify_component_aliases(params)


def _setup_deprecation_notices(config):
    config.register_deprecation_notice("test 1")
    config.register_deprecation_notice("test 2")


def test_register_deprecation_notices(config):
    _setup_deprecation_notices(config)

    assert ["test 1", "test 2"] == config._deprecation_notices


def test_print_deprecation_notices_no_notices(config, capsys):
    config.print_deprecation_notices()
    captured = capsys.readouterr()
    assert "" == captured.out


def test_print_deprecation_notices(config, capsys):
    _setup_deprecation_notices(config)

    config.print_deprecation_notices()
    captured = capsys.readouterr()
    assert (
        textwrap.dedent(
            """
            Commodore notices:
             > test 1
             > test 2
            """
        )
        == captured.out
    )
