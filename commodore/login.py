import time
import threading
import webbrowser
import json

from oauthlib.oauth2 import WebApplicationClient

import requests

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from .config import Config

client = WebApplicationClient("syn-lieutenant-dev")

app = FastAPI()


@app.get("/")
async def callback(code: str = ""):
    token_url, headers, body = client.prepare_token_request(
        "https://id.test.vshn.net/auth/realms/VSHN-main-dev-realm/protocol/openid-connect/token",
        # authorization_response="http://localhost:8000",
        redirect_url="http://localhost:8000",
        code=code,
    )
    token_response = requests.post(
        token_url,
        headers=headers,
        data=body,
    )

    print(
        client.parse_request_body_response(json.dumps(token_response.json()))[
            "id_token"
        ]
    )
    return HTMLResponse(
        status_code=200,
        content="""
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
""",
    )


def _start_server():
    uvicorn.run(app, port=8000, log_level="error")


def login(config: Config):
    server_thread = threading.Thread(target=_start_server)
    server_thread.start()

    # TODO(glrf) That's racy
    request_uri = client.prepare_request_uri(
        "https://id.test.vshn.net/auth/realms/VSHN-main-dev-realm/protocol/openid-connect/auth",
        redirect_uri="http://localhost:8000",
        scope=["openid", "email", "profile"],
    )
    print(request_uri + "\n")
    webbrowser.open(request_uri)
    server_thread.join()
