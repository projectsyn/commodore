import json, requests
from git import Repo
from url_normalize import url_normalize

def fetch_git_repository(repository_url, directory):
    Repo.clone_from(url_normalize(repository_url), directory)

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
