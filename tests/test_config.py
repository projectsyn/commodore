from __future__ import annotations

import json
import time
import textwrap

from pathlib import Path as P

from unittest.mock import patch
from typing import Any, Iterable, Optional

import click
import jwt
import pytest
import responses

from commodore.config import (
    Config,
    set_fact_value,
    parse_dynamic_fact_value,
    parse_dynamic_facts_from_cli,
)
from commodore.package import Package
from commodore.multi_dependency import dependency_key


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


def test_verify_toplevel_component_aliases_exception(config):
    alias_data = {"baz": "bar"}
    config.register_component_aliases(alias_data)
    params = {"bar": {"multi_instance": True, "namespace": "syn-bar"}}

    with pytest.raises(click.ClickException) as e:
        config.verify_component_aliases(params)

    assert "Component bar with alias baz does not support instantiation." in str(
        e.value
    )


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
        return {
            "id_token": jwt.encode(
                {"exp": time.time() + 100, "from_cache": True},
                "secret",
                algorithm="HS256",
            )
        }
    elif url == "https://expired.example.com":
        return {
            "id_token": jwt.encode(
                {"exp": time.time() - 100, "from_cache": True},
                "secret",
                algorithm="HS256",
            )
        }

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


def test_register_get_package(config: Config, tmp_path: P, mockdep):
    # No preregistered packages
    assert config.get_packages() == {}

    p = Package("test", mockdep, tmp_path / "pkg")
    config.register_package("test", p)

    assert config.get_packages() == {"test": p}


def test_register_get_dependency(config: Config, tmp_path: P):
    repo_url = "https://git.example.com/repo.git"

    # No dependencies registered initially
    assert len(config._dependency_repos) == 0

    md = config.register_dependency_repo(repo_url)

    depkey = dependency_key(repo_url)

    assert len(config._dependency_repos) == 1
    assert config._dependency_repos.get(depkey) == md


def test_register_get_dependency_deduplicates(config: Config, tmp_path: P):
    repo_url_1 = "https://git.example.com/repo1.git"
    repo_url_2 = "https://git.example.com/repo2.git"

    assert len(config._dependency_repos) == 0

    md = config.register_dependency_repo(repo_url_1)

    depkey = dependency_key(repo_url_1)

    assert len(config._dependency_repos) == 1
    assert config._dependency_repos.get(depkey) == md

    md1_dup = config.register_dependency_repo(repo_url_1)

    assert len(config._dependency_repos) == 1
    assert md1_dup == md

    md2 = config.register_dependency_repo(repo_url_2)

    depkey2 = dependency_key(repo_url_2)

    assert len(config._dependency_repos) == 2
    assert config._dependency_repos.get(depkey2) == md2
    assert set(config._dependency_repos.keys()) == {depkey, depkey2}


def test_register_dependency_prefer_ssh(config: Config, tmp_path: P):
    repo_url_https = "https://git.example.com/repo.git"
    repo_url_ssh = "ssh://git@git.example.com/repo.git"

    md = config.register_dependency_repo(repo_url_https)
    assert md.url == repo_url_https

    md2 = config.register_dependency_repo(repo_url_ssh)
    assert md2 == md
    assert md.url == repo_url_ssh

    md3 = config.register_dependency_repo(repo_url_https)
    assert md3 == md
    assert md.url == repo_url_ssh


@pytest.mark.parametrize(
    "key,base_dict,expected_dict",
    [
        ("toplevel", {}, {"toplevel": "sentinel"}),
        ("path.to.key", {}, {"path": {"to": {"key": "sentinel"}}}),
        ("path.to.key", {"path": {"to": "value"}}, {"path": {"to": "value"}}),
        (
            "path.to.key",
            {"path": {"to": {"other": "value"}}},
            {"path": {"to": {"other": "value", "key": "sentinel"}}},
        ),
        ("path.", {}, {}),
        ("path..foo", {}, {}),
        (".foo", {}, {}),
    ],
)
def test_set_fact_value(
    key: str,
    base_dict: dict[str, Any],
    expected_dict: dict[str, Any],
):
    set_fact_value(base_dict, key, "sentinel")
    assert base_dict == expected_dict


@pytest.mark.parametrize(
    "value,expected",
    [
        ("foo", "foo"),
        ("test:foo", "test:foo"),
        ("json:foo", None),
        ('json:{"foo":"bar"', None),
        ('json:"foo"', "foo"),
        ("json:1", 1),
        ('json:["a"]', ["a"]),
        ('json:{"test":{"key":"value"}}', {"test": {"key": "value"}}),
    ],
)
def test_parse_dynamic_fact_value(value: str, expected: Any):
    parsed = parse_dynamic_fact_value(value)
    assert parsed == expected


@pytest.mark.parametrize(
    "args,expected",
    [
        ([], {}),
        (["key"], {}),
        (["key="], {}),
        (["="], {}),
        (["=value"], {}),
        (['key=json:""'], {"key": ""}),
        (["key=value"], {"key": "value"}),
        (["key=value", "foo=bar"], {"key": "value", "foo": "bar"}),
        (["key=value=x"], {"key": "value=x"}),
        (["key=value", "key=another"], {"key": "another"}),
        (["key=value", "key.foo=bar"], {"key": "value"}),
        (["key.foo=bar", "key=value"], {"key": "value"}),
        (["key.foo=bar", "key.baz=qux"], {"key": {"foo": "bar", "baz": "qux"}}),
        (["key=json:[1,2,3]"], {"key": [1, 2, 3]}),
        (["key=json:[1,2,3"], {}),
        (["path.to.key=json:foo"], {}),
    ],
)
def test_parse_dynamic_facts_from_cli(args: Iterable[str], expected: dict[str, Any]):
    dynamic_facts = parse_dynamic_facts_from_cli(args)
    assert dynamic_facts == expected


@responses.activate
@pytest.mark.parametrize(
    "api_url,discovery_resp,expected_client,expected_url",
    [
        ("https://syn.example.com", {}, None, None),
        # Non-JSON is ignored
        ("https://syn.example.com", "oidc", None, None),
        # Broken JSON is ignored
        ("https://syn.example.com", '"oidc":{"tes: 1}', None, None),
        # Unexpected data format is ignored
        ("https://syn.example.com", {"oidc": {"client_id": "test"}}, None, None),
        # Partial responses are propagated into the config object
        (
            "https://syn.example.com",
            {"oidc": {"clientId": "test-client"}},
            "test-client",
            None,
        ),
        (
            "https://syn.example.com",
            {
                "oidc": {
                    "clientId": "test-client",
                    "discoveryUrl": "https://oidc.example.com",
                },
            },
            "test-client",
            "https://oidc.example.com",
        ),
    ],
)
def test_config_discover_oidc_config(
    tmp_path: P,
    api_url: str,
    discovery_resp: Any,
    expected_client: str,
    expected_url: str,
):
    if isinstance(discovery_resp, dict):
        ct = "application/json"
        resp_body = json.dumps(discovery_resp)
    else:
        resp_body = f"{discovery_resp}"
        ct = "text/plain"

    responses.add(
        responses.GET, url=api_url, content_type=ct, body=resp_body, status=200
    )

    c = Config(tmp_path, api_url=api_url)
    c.discover_oidc_config()

    assert len(responses.calls) == 1

    assert c.oidc_client == expected_client
    assert c.oidc_discovery_url == expected_url
