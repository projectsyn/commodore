import json, requests
from url_normalize import url_normalize

def api_request(api_url, type, customer, cluster):
    if type != "inventory" and type != "targets":
        print(f"Unknown API endpoint {type}")
        return {}
    r = requests.get(url_normalize(f"{api_url}/{type}/{customer}/{cluster}"))
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
