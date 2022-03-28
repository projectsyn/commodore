import time

import pytest
import textwrap
from pathlib import Path as P

from unittest.mock import patch
from typing import Optional

import jwt

import click

from commodore.config import Config


@pytest.fixture
def config(tmp_path: P):
    return Config(
        tmp_path,
        api_url="https://syn.example.com",
        api_token="token",
    )


def test_verify_component_aliases_no_instance(config):
    alias_data = {"bar": "bar"}
    config.register_component_aliases(alias_data)
    params = {"bar": {"namespace": "syn-bar"}}

    config.verify_component_aliases(params)


def test_verify_component_aliases_explicit_no_instance(config):
    alias_data = {"bar": "bar"}
    config.register_component_aliases(alias_data)
    params = {"bar": {"_metadata": {"multi_instance": False}, "namespace": "syn-bar"}}

    config.verify_component_aliases(params)


def test_verify_component_aliases_metadata(config):
    alias_data = {"baz": "bar"}
    config.register_component_aliases(alias_data)
    params = {"bar": {"_metadata": {"multi_instance": True}, "namespace": "syn-bar"}}

    config.verify_component_aliases(params)

    assert len(config._deprecation_notices) == 0


def test_verify_component_aliases_deprecated(config):
    alias_data = {"baz": "bar"}
    config.register_component_aliases(alias_data)
    params = {"bar": {"multi_instance": True, "namespace": "syn-bar"}}

    config.verify_component_aliases(params)

    assert len(config._deprecation_notices) == 1
    depnotice = config._deprecation_notices[0]
    assert (
        "Component `bar` advertises multi-instance support in component parameter "
        + "`multi_instance`. This has been deprecated in favor of using "
        + "`_metadata.multi_instance`."
    ) in depnotice


def test_verify_component_aliases_error(config):
    alias_data = {"baz": "bar"}
    config.register_component_aliases(alias_data)
    params = {"bar": {"namespace": "syn-bar"}}

    with pytest.raises(click.ClickException):
        config.verify_component_aliases(params)


def test_verify_component_aliases_explicit_no_instance_error(config):
    alias_data = {"baz": "bar"}
    config.register_component_aliases(alias_data)
    params = {"bar": {"_metadata": {"multi_instance": False}, "namespace": "syn-bar"}}

    with pytest.raises(click.ClickException):
        config.verify_component_aliases(params)


@pytest.mark.parametrize(
    "params,expected",
    [
        (
            {
                "bar": {"namespace": "syn-bar"},
                "foo": {},
            },
            [],
        ),
        (
            {
                "bar": {
                    "namespace": "syn-bar",
                    "_metadata": {"deprecated": False, "replaced_by": "irrelevant"},
                },
                "foo": {},
            },
            [],
        ),
        (
            {
                "bar": {
                    "namespace": "syn-bar",
                    "_metadata": {"deprecated": True},
                },
                "foo": {},
            },
            ["Component bar is deprecated."],
        ),
        (
            {
                "bar": {
                    "namespace": "syn-bar",
                    "_metadata": {"deprecated": True, "replaced_by": "foo"},
                },
                "foo": {},
            },
            ["Component bar is deprecated. Use component foo instead."],
        ),
        (
            {
                "bar": {
                    "namespace": "syn-bar",
                    "_metadata": {
                        "deprecated": True,
                        "replaced_by": "foo",
                        "deprecation_notice": "See https://example.com/migrate-from-bar.html for a migration guide.",
                    },
                },
                "foo": {},
            },
            [
                "Component bar is deprecated. Use component foo instead. "
                + "See https://example.com/migrate-from-bar.html for a migration guide."
            ],
        ),
        (
            {
                "bar": {
                    "namespace": "syn-bar",
                    "_metadata": {
                        "deprecated": True,
                    },
                },
                "foo": {
                    "namespace": "syn-foo",
                    "_metadata": {
                        "deprecated": True,
                    },
                },
            },
            ["Component bar is deprecated.", "Component foo is deprecated."],
        ),
    ],
)
def test_register_component_deprecations(config, params, expected):
    alias_data = {"baz": "bar", "qux": "foo"}
    config.register_component_aliases(alias_data)

    config.register_component_deprecations(params)

    assert len(expected) == len(config._deprecation_notices)
    for en, an in zip(sorted(expected), sorted(config._deprecation_notices)):
        assert en == an


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


def mock_get_token(url: str) -> Optional[str]:
    if url == "https://syn.example.com":
        return jwt.encode(
            {"exp": time.time() + 100, "from_cache": True}, "secret", algorithm="HS256"
        )
    elif url == "https://expired.example.com":
        return jwt.encode(
            {"exp": time.time() - 100, "from_cache": True}, "secret", algorithm="HS256"
        )

    else:
        return None


@patch("commodore.tokencache.get")
def test_use_token_cache(test_patch):
    test_patch.side_effect = mock_get_token
    conf = Config(P("."), api_url="https://syn.example.com")
    t = jwt.decode(
        conf.api_token, algorithms=["RS256"], options={"verify_signature": False}
    )
    assert t["from_cache"]


@patch("commodore.tokencache.get")
def test_expired_token_cache(test_patch):
    test_patch.side_effect = mock_get_token
    conf = Config(P("."), api_url="https://expired.example.com")
    assert conf.api_token is None
