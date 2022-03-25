"""
Unit-tests for login
"""

from unittest.mock import patch
import responses

import requests

from commodore.config import Config
from commodore import login


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


@patch("webbrowser.open")
@patch("commodore.tokencache.save")
@responses.activate
def test_login(mock_tokencache, mock_browser, tmp_path):
    discovery_url = "https://idp.example.com/discovery"
    token_url = "https://idp.example.com/token"
    auth_url = "https://idp.example.com/auth"
    client = "syn-test"
    api_url = "https://syn.example.com"
    access_token = "access-123"
    id_token = "id-123"

    config = Config(
        tmp_path,
        api_url=api_url,
    )
    config.oidc_client = client
    config.oidc_discovery_url = discovery_url

    responses.add_passthru("http://localhost:18000/")
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

    mock_tokencache.side_effect = mock_tokencache_save(api_url, id_token)
    mock_browser.side_effect = mock_open_browser(auth_url)
    login.login(config)
