import pytest

import click

from commodore.config import Config


@pytest.fixture
def config():
    return Config(
        "https://syn.example.com", "token", "ssh://git@git.example.com", False
    )


def test_verify_component_aliases(config):
    alias_data = {"baz": "bar"}
    config.register_component_aliases(alias_data)
    params = {"bar": {"_instance": "default", "namespace": "syn-bar"}}

    config.verify_component_aliases(params)


def test_verify_component_aliases_error(config):
    alias_data = {"baz": "bar"}
    config.register_component_aliases(alias_data)
    params = {"bar": {"namespace": "syn-bar"}}

    with pytest.raises(click.ClickException):
        config.verify_component_aliases(params)
