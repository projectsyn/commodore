import time
import threading
import webbrowser
import json

from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

from oauthlib.oauth2 import WebApplicationClient

import requests

from .config import Config


class OIDCServer(BaseHTTPRequestHandler):
    client = WebApplicationClient("syn-lieutenant-dev")

    def do_GET(self):
        print(self.path)
        query_components = parse_qs(urlparse(self.path).query)
        code = query_components["code"]
        token_url, headers, body = self.client.prepare_token_request(
            "https://id.test.vshn.net/auth/realms/VSHN-main-dev-realm/protocol/openid-connect/token",
            redirect_url="http://localhost:8000",
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


def start_server():
    webServer = HTTPServer(("localhost", 8000), OIDCServer)
    webServer.serve_forever()


def login(config: Config):
    server_thread = threading.Thread(target=start_server)
    server_thread.start()

    # TODO(glrf) That's racy
    c = WebApplicationClient("syn-lieutenant-dev")
    request_uri = c.prepare_request_uri(
        "https://id.test.vshn.net/auth/realms/VSHN-main-dev-realm/protocol/openid-connect/auth",
        redirect_uri="http://localhost:8000",
        scope=["openid", "email", "profile"],
    )
    print(request_uri + "\n")
    webbrowser.open(request_uri)
    server_thread.join()
