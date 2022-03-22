import time
import threading
from queue import Queue
import webbrowser
import json

import click

from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

from oauthlib.oauth2 import WebApplicationClient

import requests

from .config import Config


class OIDCHandler(BaseHTTPRequestHandler):
    client: WebApplicationClient
    done: Queue

    token_url: str
    redirect_url: str

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

        print(
            self.client.parse_request_body_response(json.dumps(token_response.json()))[
                "id_token"
            ]
        )

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
    if config.oidc_client == None:
        raise click.ClickException(f"Required OIDC client not set")
    client = WebApplicationClient(config.oidc_client)

    if config.oidc_discovery_url == None:
        raise click.ClickException(f"Required OIDC discovery URL not set")
    idp_cfg = requests.get(config.oidc_discovery_url).json()

    done_queue = Queue()

    OIDCHandler.client = client
    OIDCHandler.done = done_queue

    OIDCHandler.token_url = idp_cfg["token_endpoint"]
    OIDCHandler.redirect_url = "http://localhost:8000"

    server = HTTPServer(("localhost", 8000), OIDCHandler)
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()

    # TODO(glrf) That's racy
    request_uri = client.prepare_request_uri(
        idp_cfg["authorization_endpoint"],
        redirect_uri="http://localhost:8000",
        scope=["openid", "email", "profile"],
    )
    print(f"Follow this link if it doesn't open automatically \n\n{request_uri}\n")
    webbrowser.open(request_uri)

    done_queue.get()
    server.shutdown()
    server_thread.join()
