import json, requests
from git import Repo
from url_normalize import url_normalize
from url_normalize.url_normalize import normalize_userinfo, normalize_host, normalize_path, provide_url_scheme
from url_normalize.tools import deconstruct_url, reconstruct_url

def _normalize_git_ssh(url):
    origurl = url
    if '@' in url and not url.startswith('ssh://'):
        # Assume git@host:repo format, reformat so url_normalize understands
        # the URL
        host, repo = url.split(':')
        url = f"{host}/{repo}"
    # Import heavy lifting from url_normalize, simplify for Git-SSH usecase
    url = provide_url_scheme(url, "ssh")
    urlparts = deconstruct_url(url)
    urlparts = urlparts._replace(
            userinfo=normalize_userinfo(urlparts.userinfo),
            host=normalize_host(urlparts.host),
            path=normalize_path(urlparts.path, scheme='https'),
    )
    return reconstruct_url(urlparts)

def fetch_git_repository(repository_url, directory):
    Repo.clone_from(_normalize_git_ssh(repository_url), directory)

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
