"""
Unit-tests for login
"""

from unittest.mock import patch

import json
import time
import threading

from functools import partial
from http.server import HTTPServer
from queue import Queue

import jwt
import pytest
import requests
import responses

from oauthlib.oauth2 import WebApplicationClient
from xdg.BaseDirectory import xdg_cache_home

from commodore.config import Config
from commodore import login
from commodore import tokencache


def mock_open_browser(authorization_endpoint: str, code="foobar"):
    def mock(request_uri: str):
        assert request_uri.startswith(authorization_endpoint)

        params = ""
        if code is not None:
            params = f"?code={code}"

        r = requests.get(f"http://localhost:18000/{params}")

        print(r.text)
        r.raise_for_status()

    return mock


def mock_tokencache_save(url: str, token: str):
    def mock(key: str, val: str):
        if key != url:
            raise IOError(f"wrong url, expected https://syn.example.com, got {key}")
        if val != token:
            raise IOError(f"wrong token, expected {token}, got {val}")

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


@pytest.mark.parametrize(
    "api_url,path,expected_status,expected_text",
    [
        ("https://syn.example.com", "/healthz", 200, "ok"),
        (
            "https://syn.example.com",
            "/?foo=bar",
            422,
            "invalid callback: no code provided",
        ),
        (
            "https://syn.example.com",
            "/?code=foobar",
            500,
            "failed to connect to IdP: 500 Server Error: "
            + "Internal Server Error for url: https://idp.example.com/token",
        ),
        ("https://syn.example.com", "/?code=foobar", 500, "no id_token provided"),
        ("https://syn.example.com", "/?code=foobar", 500, "failed to save token"),
        (None, "/?code=foobar", 200, "\n<!DOCTYPE html>"),
        ("https://syn.example.com", "/?code=foobar", 200, "\n<!DOCTYPE html>"),
    ],
)
@responses.activate
@patch("commodore.tokencache.save")
def test_callback_get(
    mock_tokencache,
    capsys,
    config: Config,
    api_url,
    path,
    expected_status,
    expected_text,
):
    config.oidc_client = "test-client"
    config.api_url = api_url
    token_url = "https://idp.example.com/token"
    done_queue = Queue()
    expected_token = {"access_token": "access-123", "id_token": "id-123"}
    if expected_text == "failed to save token":
        expected_token = {"id_token": "foo", "access_token": "bar"}
    mock_tokencache.side_effect = mock_tokencache_save(config.api_url, expected_token)

    h = partial(
        login.OIDCCallbackHandler,
        WebApplicationClient(config.oidc_client),
        token_url,
        config.api_url,
        done_queue,
    )
    # Let Python pick a port
    server = HTTPServer(("", 0), h)
    port = server.server_port
    t = threading.Thread(target=server.serve_forever)
    t.daemon = True
    t.start()

    responses.add_passthru(f"http://localhost:{port}")
    resp_data = {"access_token": "access-123", "id_token": "id-123"}
    resp_status = 200

    if expected_text == "no id_token provided":
        del resp_data["id_token"]

    if expected_text.startswith("failed to connect to IdP"):
        resp_status = 500

    responses.add(
        responses.POST,
        token_url,
        json=resp_data,
        status=resp_status,
    )

    resp = requests.get(f"http://localhost:{port}{path}")
    if resp.status_code != expected_status:
        print(resp.text)

    assert resp.status_code == expected_status
    assert resp.text.startswith(expected_text)

    if api_url is None:
        captured = capsys.readouterr()
        assert captured.out == "id-123\n"

    server.shutdown()
    t.join()


def test_run_callback_server(config, tmp_path):
    config.oidc_client = "test-client"
    token_url = "https://idp.example.com/token"
    c = WebApplicationClient(config.oidc_client)
    s = login.OIDCCallbackServer(c, token_url, config.api_url)

    s.start()

    resp = requests.get("http://localhost:18000/healthz")
    assert resp.status_code == 200
    assert resp.text == "ok"

    # calls to /healthz don't close the server, so we make a second request
    resp = requests.get("http://localhost:18000/?foo=bar")
    assert resp.status_code == 422
    assert resp.text == "invalid callback: no code provided"

    s.join()
