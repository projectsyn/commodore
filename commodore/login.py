from typing import Optional
import threading
from queue import Queue
import webbrowser
import json

from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

import click
import requests

from oauthlib.oauth2 import WebApplicationClient

from .config import Config
from . import tokencache


class OIDCHandler(BaseHTTPRequestHandler):
    client: WebApplicationClient
    done: Queue

    token_url: str
    redirect_url: str

    lieutenant_url: Optional[str]

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


def login(config: Config):
    if config.oidc_client is None:
        raise click.ClickException("Required OIDC client not set")
    client = WebApplicationClient(config.oidc_client)

    if config.oidc_discovery_url is None:
        raise click.ClickException("Required OIDC discovery URL not set")
    idp_cfg = requests.get(config.oidc_discovery_url).json()

    done_queue: Queue = Queue()

    OIDCHandler.client = client
    OIDCHandler.done = done_queue

    OIDCHandler.token_url = idp_cfg["token_endpoint"]
    OIDCHandler.redirect_url = "http://localhost:18000"
    OIDCHandler.lieutenant_url = config.api_url

    server = HTTPServer(("localhost", 18000), OIDCHandler)
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()

    # That's racy, but it should work most of the time and if not the browser shoudld retry
    request_uri = client.prepare_request_uri(
        idp_cfg["authorization_endpoint"],
        redirect_uri="http://localhost:18000",
        scope=["openid", "email", "profile"],
    )

    print(f"Follow this link if it doesn't open automatically \n\n{request_uri}\n")
    webbrowser.open(request_uri)

    done_queue.get()
    server.shutdown()
    server_thread.join()
