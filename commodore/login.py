from __future__ import annotations

import json
import sys
import threading
import time
import webbrowser

from functools import partial
from queue import Queue
from typing import Optional, Any

from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

import click
import jwt
import requests

# pylint: disable=redefined-builtin
from requests.exceptions import ConnectionError, HTTPError

from oauthlib.oauth2 import WebApplicationClient

from .config import Config
from . import tokencache


class OIDCError(Exception):
    pass


class OIDCCallbackServer:
    done_queue: Queue = Queue()
    thread: threading.Thread
    server: HTTPServer

    def __init__(
        self,
        client: WebApplicationClient,
        token_url: str,
        lieutenant_url: Optional[str],
        port: int = 18000,
    ):
        self.client = client
        self.token_endpoint = token_url
        self.lieutenant_url = lieutenant_url

        handler = partial(
            OIDCCallbackHandler, client, token_url, lieutenant_url, self.done_queue
        )

        self.server = HTTPServer(("", port), handler)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.daemon = True

    def start(self):
        self.thread.start()

    def join(self):
        self.done_queue.get()
        self.server.shutdown()
        self.thread.join()


class OIDCCallbackHandler(BaseHTTPRequestHandler):
    client: WebApplicationClient
    done: Queue

    token_url: str
    redirect_url: str

    lieutenant_url: Optional[str]

    def __init__(
        self,
        client: WebApplicationClient,
        token_url: str,
        lieutenant_url: Optional[str],
        done_queue: Queue,
        *args,
        **kwargs,
    ):
        self.client = client
        self.done = done_queue
        self.lieutenant_url = lieutenant_url
        self.token_url = token_url
        self.redirect_url = "http://localhost:18000"
        super().__init__(*args, **kwargs)

    # pylint: disable=unused-argument
    # pylint: disable=redefined-builtin
    def log_message(self, format, *args):
        return

    def do_GET(self):
        if self.path == "/healthz":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(str.encode("ok"))
            return

        query_components = parse_qs(urlparse(self.path).query)
        if "code" not in query_components or len(query_components["code"]) == 0:
            self.close(422, "invalid callback: no code provided")
            return

        code = query_components["code"][0]
        try:
            tokens = self.get_oidc_tokens(code)
        except (ConnectionError, HTTPError) as e:
            self.close(500, f"failed to connect to IdP: {e}")
            return

        id_token = tokens.get("id_token")

        if id_token is None:
            self.close(500, "no id_token provided")
            return

        if self.lieutenant_url is None:
            print(id_token)
        else:
            try:
                tokencache.save(self.lieutenant_url, tokens)
            except IOError as e:
                self.close(500, f"failed to save token {e}")
                return

        self.close(200, success_page)
        return

    def get_oidc_tokens(self, code) -> dict[str, Any]:
        token_url, headers, body = self.client.prepare_token_request(
            self.token_url,
            redirect_url=self.redirect_url,
            code=code,
        )

        token_response = requests.post(
            token_url,
            headers=headers,
            data=body,
        )
        token_response.raise_for_status()

        return self.client.parse_request_body_response(token_response.text)

    def close(self, code: int, msg: str):
        self.send_response(code)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(str.encode(msg))
        self.done.put(True)


success_page = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Authorized</title>
    <script>
        setTimeout(window.close, 5000);
    </script>
     <style>
        body {
            background-color: #eee;
            margin: 0;
            padding: 0;
            font-family: sans-serif;
        }
        .placeholder {
            margin: 2em;
            padding: 2em;
            background-color: #fff;
            border-radius: 1em;
        }
    </style>
</head>
<body>
    <div class="placeholder">
        <h1>Authorized</h1>
        <p>You can close this window.</p>
    </div>
</body>
</html>
"""


def get_idp_cfg(discovery_url: str) -> Any:
    try:
        r = requests.get(discovery_url)
    except ConnectionError as e:
        raise OIDCError(f"Unable to connect to IDP at {discovery_url}") from e
    try:
        resp = json.loads(r.text)
    except json.JSONDecodeError as e:
        raise OIDCError("Client error: Unable to parse JSON") from e
    try:
        r.raise_for_status()
    except HTTPError as e:
        raise OIDCError(f"IDP returned {r.status_code} {e}") from e
    else:
        return resp


def refresh_tokens(
    config: Config, client: WebApplicationClient, token_endpoint: str
) -> bool:
    """Try refreshing the access and id tokens using the current refresh token.

    Tokens are fetched from the token cache based on the data in `config`. The new
    tokens are written to the token cache.

    Returns `True` if refreshing the token was successful."""
    if config.api_url is None:
        # We can't refresh tokens if we don't know the API URL to fetch the old tokens
        # from the cache.
        return False

    tokens = tokencache.get(config.api_url)
    refresh_token = tokens.get("refresh_token")
    if refresh_token is None:
        return False
    # We don't verify the signature, we just want to know if the refresh token is
    # expired.
    try:
        t = jwt.decode(
            refresh_token, algorithms=["RS256"], options={"verify_signature": False}
        )
    except jwt.exceptions.InvalidTokenError:
        # We can't parse the refresh token, notify caller that they need to request a
        # fresh set of tokens.
        return False

    if "exp" in t and t["exp"] > time.time():
        # Only try to refresh the tokens if the refresh token isn't expired yet.
        token_url, headers, body = client.prepare_refresh_token_request(
            token_url=token_endpoint,
            refresh_token=refresh_token,
            client_id=config.oidc_client,
        )
        try:
            token_response = requests.post(token_url, headers=headers, data=body)
            token_response.raise_for_status()
        except (ConnectionError, HTTPError) as e:
            click.echo(f" > Failed to refresh OIDC token with {e}")
            return False

        # If refresh request was successful, parse response and store new
        # tokens in tokencache
        new_tokens = client.parse_request_body_response(token_response.text)
        tokencache.save(config.api_url, new_tokens)
        return True

    return False


def login(config: Config):
    config.discover_oidc_config()

    if config.oidc_client is None:
        raise click.ClickException("Required OIDC client not set")
    if config.oidc_discovery_url is None:
        raise click.ClickException("Required OIDC discovery URL not set")

    if config.api_token:
        # Short-circuit if we already have a valid API token
        return

    client = WebApplicationClient(config.oidc_client)
    idp_cfg = get_idp_cfg(config.oidc_discovery_url)
    if refresh_tokens(config, client, idp_cfg["token_endpoint"]):
        # Short-circuit if refreshing the token was successful.
        return

    # Request new token through login flow if we weren't able to refresh the existing
    # token.
    server = OIDCCallbackServer(client, idp_cfg["token_endpoint"], config.api_url)
    server.start()

    # Wait for server to run
    r = requests.Response()
    r.status_code = 500
    while r.status_code != 200:
        try:
            r = requests.get("http://localhost:18000/healthz")
        except ConnectionError:
            pass

    request_uri = client.prepare_request_uri(
        idp_cfg["authorization_endpoint"],
        redirect_uri="http://localhost:18000",
        scope=["openid", "email", "profile"],
    )
    opened = webbrowser.open(request_uri)
    if not opened:
        print(
            f"Failed to open browser, follow this link to login\n\n{request_uri}\n",
            file=sys.stderr,
        )

    server.join()


def fetch_token(config) -> str:
    """Return cached API token if it's fresh enough.

    Otherwise, call login() and return the resulting token.
    """
    if config.api_token:
        return config.api_token

    login(config)
    return config.api_token
