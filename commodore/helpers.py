import json, requests
from requests.exceptions import ConnectionError
from url_normalize import url_normalize

class ApiError(Exception):
    def __init__(self, message):
        self.message = message

def api_request(api_url, type, customer, cluster):
    if type != "inventory" and type != "targets":
        print(f"Unknown API endpoint {type}")
        return {}
    try:
        r = requests.get(url_normalize(f"{api_url}/{type}/{customer}/{cluster}"))
    except ConnectionError as e:
        raise ApiError(f"Unable to connect to SYNventory at {api_url}") from e
    resp = json.loads(r.text)
    if r.status_code == 404:
        print(resp['message'])
        return {}
    else:
        return resp

def clean():
    import shutil
    shutil.rmtree("inventory", ignore_errors=True)
    shutil.rmtree("dependencies", ignore_errors=True)
    shutil.rmtree("compiled", ignore_errors=True)

def kapitan_compile():
    # TODO: maybe use kapitan.targets.compile_targets directly?
    import shlex, subprocess
    subprocess.run(shlex.split("kapitan compile"))
