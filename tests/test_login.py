"""
Unit-tests for login
"""

from unittest.mock import patch

import json
import time

import jwt
import pytest
import requests
import responses

from oauthlib.oauth2 import WebApplicationClient
from xdg.BaseDirectory import xdg_cache_home

from commodore.config import Config
from commodore import login
from commodore import tokencache


def mock_open_browser(authorization_endpoint: str):
    def mock(request_uri: str):
        assert request_uri.startswith(authorization_endpoint)

        r = requests.get("http://localhost:18000/?code=foobar")

        print(r.text)
        r.raise_for_status()

    return mock


def mock_tokencache_save(url: str, token: str):
    def mock(key: str, val: str):
        if key != url:
            raise IOError(f"wrong url, expected https://syn.example.com, got {key}")
        if val != token:
            raise IOError(f"wrong token, expected blub, got {val}")

    return mock


def _setup_responses(api_url, auth_url, id_token):
    discovery_url = "https://idp.example.com/discovery"
    token_url = "https://idp.example.com/token"
    client = "syn-test"
    access_token = "access-123"

    responses.add_passthru("http://localhost:18000/")
    responses.add(
        responses.GET,
        api_url,
        json={"oidc": {"discoveryUrl": discovery_url, "clientId": client}},
        status=200,
    )
    responses.add(
        responses.GET,
        discovery_url,
        json={
            "authorization_endpoint": auth_url,
            "token_endpoint": token_url,
        },
        status=200,
    )
    responses.add(
        responses.POST,
        token_url,
        json={"id_token": id_token, "access_token": access_token},
        status=200,
    )


@patch("webbrowser.open")
@patch("commodore.tokencache.save")
@responses.activate
def test_login(mock_tokencache, mock_browser, config: Config, tmp_path):
    auth_url = "https://idp.example.com/auth"
    id_token = "id-123"

    _setup_responses(config.api_url, auth_url, id_token)

    mock_tokencache.side_effect = mock_tokencache_save(config.api_url, id_token)
    mock_browser.side_effect = mock_open_browser(auth_url)

    login.login(config)


def mocked_login(expected_token):
    def mock(config: Config):
        with open(f"{xdg_cache_home}/commodore/token", "w") as f:
            json.dump({config.api_url: {"id_token": expected_token}}, f)

    return mock


@responses.activate
@pytest.mark.parametrize("cached", [True, False])
@patch("commodore.login.login")
def test_fetch_token(mock_login, config: Config, tmp_path, fs, cached):
    # The `config` test fixture sets api_token='token'. We clear this configuration here
    # to test the token fetching logic.
    config.api_token = None
    auth_url = "https://idp.example.com/auth"
    expected_token_payload = {"marker": "id-123", "exp": time.time() + 600}
    cache_contents = {}
    if cached:
        expected_token_payload["marker"] = "id-456"

    expected_token = jwt.encode(expected_token_payload, "aaaaaa")
    if cached:
        cache_contents = {config.api_url: {"id_token": expected_token}}

    _setup_responses(config.api_url, auth_url, expected_token)
    fs.create_file(
        f"{xdg_cache_home}/commodore/token", contents=json.dumps(cache_contents)
    )

    mock_login.side_effect = mocked_login(expected_token)

    token = login.fetch_token(config)

    assert token == expected_token


@responses.activate
def test_refresh_tokens(config: Config, tmp_path, fs):
    config.api_token = None
    config.oidc_client = "test-client"

    token_url = "https://idp.example.com/token"
    current_id_token = {
        "marker": "id-123",
        # Make id token expired, even though `refresh_tokens()` doesn't check
        "exp": time.time() - 10,
    }
    current_refresh_token = {
        "marker": "r-123",
        "exp": time.time() + 600,
    }

    new_id_token = {
        "marker": "id-456",
        "exp": time.time() + 600,
    }
    new_refresh_token = {
        "marker": "r-456",
        "exp": time.time() + 1800,
    }

    current_tokens = {
        "id_token": jwt.encode(current_id_token, "aaaaaa"),
        "refresh_token": jwt.encode(current_refresh_token, "aaaaaa"),
    }
    new_tokens = {
        "access_token": "dummy-access-token-456",
        "id_token": jwt.encode(new_id_token, "aaaaaa"),
        "refresh_token": jwt.encode(new_refresh_token, "aaaaaa"),
    }
    cache_contents = {config.api_url: current_tokens}

    responses.add(
        responses.POST,
        token_url,
        json=new_tokens,
        status=200,
        match=[
            responses.matchers.urlencoded_params_matcher(
                {
                    "grant_type": "refresh_token",
                    "client_id": config.oidc_client,
                    "refresh_token": current_tokens["refresh_token"],
                }
            )
        ],
    )
    fs.create_file(
        f"{xdg_cache_home}/commodore/token", contents=json.dumps(cache_contents)
    )

    c = WebApplicationClient(config.oidc_client)
    refreshed = login.refresh_tokens(config, c, token_url)

    assert len(responses.calls) == 1
    assert refreshed
    assert tokencache.get(config.api_url).get("id_token") == new_tokens["id_token"]
    assert (
        tokencache.get(config.api_url).get("refresh_token")
        == new_tokens["refresh_token"]
    )
    assert config.api_token == new_tokens["id_token"]


@pytest.mark.parametrize(
    "expired_refresh_token,broken_refresh_token",
    [(False, False), (False, True), (True, False)],
)
@pytest.mark.parametrize("api_url", [None, "https://syn.example.com"])
def test_refresh_tokens_not_needed(
    config: Config, tmp_path, fs, expired_refresh_token, broken_refresh_token, api_url
):
    config.api_url = api_url
    config.api_token = None
    config.oidc_client = "test-client"
    token_url = "https://idp.example.com/token"

    id_token = {"marker": "id", "exp": time.time() - 10}
    tokens = {
        "id_token": jwt.encode(id_token, "aaaaaa"),
    }
    if expired_refresh_token:
        tokens["refresh_token"] = jwt.encode(
            {"marker": "R", "exp": time.time() - 10}, "aaaaaa"
        )
    if broken_refresh_token:
        rt = jwt.encode({"marker": "R", "exp": time.time() + 600}, "aaaaaa")
        tokens["refresh_token"] = f"X{rt[1:]}"
    cache_contents = {config.api_url: tokens}
    fs.create_file(
        f"{xdg_cache_home}/commodore/token", contents=json.dumps(cache_contents)
    )

    c = WebApplicationClient(config.oidc_client)
    refreshed = login.refresh_tokens(config, c, token_url)

    assert not refreshed
