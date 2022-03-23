from typing import Optional, Any
import threading
from queue import Queue
import webbrowser
import json
from functools import partial


from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

import click
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
    ):
        self.client = client
        self.token_endpoint = token_url
        self.lieutenant_url = lieutenant_url

        handler = partial(
            OIDCCallbackHandler, client, token_url, lieutenant_url, self.done_queue
        )

        self.server = HTTPServer(("localhost", 18000), handler)
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
        query_components = parse_qs(urlparse(self.path).query)
        code = query_components["code"]

        if len(code) == 0:
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            return

        token_url, headers, body = self.client.prepare_token_request(
            self.token_url,
            redirect_url=self.redirect_url,
            code=code[0],
        )
        token_response = requests.post(
            token_url,
            headers=headers,
            data=body,
        )

        id_token = self.client.parse_request_body_response(
            json.dumps(token_response.json())
        )["id_token"]
        if self.lieutenant_url is None:
            print(id_token)
        else:
            tokencache.save(self.lieutenant_url, id_token)

        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(str.encode(success_page))

        self.done.put(True)
        return


success_page = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Authorized</title>
    <script>
        window.close()
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
    if config.oidc_client is None:
        raise click.ClickException("Required OIDC client not set")
    if config.oidc_discovery_url is None:
        raise click.ClickException("Required OIDC discovery URL not set")

    client = WebApplicationClient(config.oidc_client)
    idp_cfg = get_idp_cfg(config.oidc_discovery_url)

    server = OIDCCallbackServer(client, idp_cfg["token_endpoint"], config.api_url)
    server.start()

    # That's racy, but it should work most of the time and if not the browser should retry
    request_uri = client.prepare_request_uri(
        idp_cfg["authorization_endpoint"],
        redirect_uri="http://localhost:18000",
        scope=["openid", "email", "profile"],
    )
    print(f"Follow this link if it doesn't open automatically \n\n{request_uri}\n")
    webbrowser.open(request_uri)

    server.join()
