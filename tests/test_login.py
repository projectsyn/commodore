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

from xdg.BaseDirectory import xdg_cache_home

from commodore.config import Config
from commodore import login


@pytest.fixture
def config(tmp_path) -> Config:
    return Config(tmp_path, api_url="https://syn.example.com")


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
def test_login(mock_tokencache, mock_browser, config, tmp_path):
    auth_url = "https://idp.example.com/auth"
    id_token = "id-123"

    _setup_responses(config.api_url, auth_url, id_token)

    mock_tokencache.side_effect = mock_tokencache_save(config.api_url, id_token)
    mock_browser.side_effect = mock_open_browser(auth_url)

    login.login(config)


@patch("webbrowser.open")
@responses.activate
@pytest.mark.parametrize("cached", [True, False])
def test_fetch_token(mock_browser, config, tmp_path, fs, cached):
    auth_url = "https://idp.example.com/auth"
    expected_token_payload = {"marker": "id-123", "exp": time.time() + 600}
    cache_contents = {}
    if cached:
        expected_token_payload["marker"] = "id-456"

    expected_token = jwt.encode(expected_token_payload, "aaaaaa")
    if cached:
        cache_contents = {config.api_url: expected_token}

    _setup_responses(config.api_url, auth_url, expected_token)
    fs.create_file(
        f"{xdg_cache_home}/commodore/token", contents=json.dumps(cache_contents)
    )

    mock_browser.side_effect = mock_open_browser(auth_url)

    token = login.fetch_token(config)

    assert token == expected_token
