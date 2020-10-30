import pytest
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
