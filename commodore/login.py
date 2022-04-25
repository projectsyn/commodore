import json
import sys
import threading
import webbrowser

from functools import partial
from queue import Queue
from typing import Optional, Any

from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from url_normalize import url_normalize

import click
import requests

# pylint: disable=redefined-builtin
from requests.exceptions import ConnectionError, HTTPError, RequestException

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
    ):
        self.client = client
        self.token_endpoint = token_url
        self.lieutenant_url = lieutenant_url

        handler = partial(
            OIDCCallbackHandler, client, token_url, lieutenant_url, self.done_queue
        )

        self.server = HTTPServer(("", 18000), handler)
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
            id_token = self.get_oidc_token(code)
        except (ConnectionError, HTTPError) as e:
            self.close(500, f"failed to connect to IdP: {e}")
            return

        if id_token is None:
            self.close(500, "no id_token provided")
            return

        if self.lieutenant_url is None:
            print(id_token)
        else:
            try:
                tokencache.save(self.lieutenant_url, id_token)
            except IOError as e:
                self.close(500, f"failed to save token {e}")
                return

        self.close(200, success_page)
        return

    def get_oidc_token(self, code) -> Optional[str]:
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

        token = self.client.parse_request_body_response(token_response.text)
        if "id_token" in token:
            return token["id_token"]
        return None

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


def login(config: Config):
    if (
        config.oidc_client is None
        and config.oidc_discovery_url is None
        and config.api_url is not None
    ):
        api_cfg: Any = {}
        try:
            r = requests.get(url_normalize(config.api_url))
            api_cfg = json.loads(r.text)
        except (RequestException, json.JSONDecodeError) as e:
            # We do this on a best effort basis
            click.echo(f" > Unable to auto-discover OIDC config: {e}")
        if "oidc" in api_cfg:
            config.oidc_client = api_cfg["oidc"]["clientId"]
            config.oidc_discovery_url = api_cfg["oidc"]["discoveryUrl"]

    if config.oidc_client is None:
        raise click.ClickException("Required OIDC client not set")
    if config.oidc_discovery_url is None:
        raise click.ClickException("Required OIDC discovery URL not set")

    client = WebApplicationClient(config.oidc_client)
    idp_cfg = get_idp_cfg(config.oidc_discovery_url)

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
    print(
        f"Follow this link if it doesn't open automatically \n\n{request_uri}\n",
        file=sys.stderr,
    )
    webbrowser.open(request_uri)

    server.join()


def fetch_token(config) -> str:
    """Return cached API token if it's fresh enough.

    Otherwise, call login() and return the resulting token.
    """
    if config.api_token:
        return config.api_token

    login(config)
    return config.api_token
