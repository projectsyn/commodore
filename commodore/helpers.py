import click, json, requests, shutil
from requests.exceptions import ConnectionError
from url_normalize import url_normalize

class ApiError(Exception):
    def __init__(self, message):
        self.message = message

def api_request(api_url, type, customer, cluster, is_json=True):
    if type != "inventory" and type != "targets":
        print(f"Unknown API endpoint {type}")
        return {}
    try:
        r = requests.get(url_normalize(f"{api_url}/{type}/{customer}/{cluster}"))
    except ConnectionError as e:
        raise ApiError(f"Unable to connect to SYNventory at {api_url}") from e
    if is_json:
        resp = json.loads(r.text)
    else:
        resp = r.text

    if r.status_code == 404:
        if is_json:
            print(resp['message'])
        return {}
    else:
        return resp

def _verbose_rmtree(tree, *args, **kwargs):
    click.echo(f" > deleting {tree}/")
    shutil.rmtree(tree, *args, **kwargs)

def clean(cfg):
    if cfg.debug:
        rmtree = _verbose_rmtree
    else:
        rmtree = shutil.rmtree
    click.secho("Cleaning working tree", bold=True)
    rmtree("inventory", ignore_errors=True)
    rmtree("dependencies", ignore_errors=True)
    rmtree("compiled", ignore_errors=True)
    rmtree("catalog", ignore_errors=True)

def kapitan_compile():
    # TODO: maybe use kapitan.targets.compile_targets directly?
    import shlex, subprocess, sys
    click.secho("Compiling catalog...", bold=True)
    return subprocess.run(shlex.split("kapitan compile --fetch -J . dependencies"))

def rm_tree_contents(dir):
    """
    Delete all files in directory `dir`, but do not delete the directory
    itself.
    """
    import glob, os
    if not os.path.isdir(dir):
        raise ValueError("Expected directory as argument")
    for f in glob.glob(f"{dir}/*"):
        if os.path.isdir(f):
            shutil.rmtree(f)
        else:
            os.unlink(f)
