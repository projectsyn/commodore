import click, json, requests, shutil, yaml
from requests.exceptions import ConnectionError, HTTPError
from url_normalize import url_normalize
from pathlib import Path as P

def yaml_load(file):
    """
    Load single-document YAML and return document
    """
    with open(file, 'r') as f:
        return yaml.safe_load(f)

def yaml_load_all(file):
    """
    Load multi-document YAML and return documents in list
    """
    with open(file, 'r') as f:
        return list(yaml.safe_load_all(f))

def yaml_dump(obj, file):
    """
    Dump obj as single-document YAML
    """
    with open(file, 'w') as outf:
        yaml.dump(obj, outf)

def yaml_dump_all(obj, file):
    """
    Dump obj as multi-document YAML
    """
    with open(file, 'w') as outf:
        yaml.dump_all(obj, outf)

class ApiError(Exception):
    def __init__(self, message):
        self.message = message

def api_request(api_url, type, customer, cluster):
    if type != 'inventory' and type != 'targets':
        raise ApiError(f"Client error: Unknown API endpoint: {type}")
    try:
        r = requests.get(url_normalize(f"{api_url}/{type}/{customer}/{cluster}"))
    except ConnectionError as e:
        raise ApiError(f"Unable to connect to SYNventory at {api_url}") from e
    try:
        resp = json.loads(r.text)
    except:
        resp = { 'message': 'Client error: Unable to parse JSON' }
    try:
        r.raise_for_status()
    except HTTPError as e:
        extra_msg = ''
        if r.status_code == 404:
            extra_msg = f": {resp['message']}"
        raise ApiError(f"API returned {r.status_code}{extra_msg}") from e
    else:
        return resp

def _verbose_rmtree(tree, *args, **kwargs):
    click.echo(f' > deleting {tree}/')
    shutil.rmtree(tree, *args, **kwargs)

def clean(cfg):
    if cfg.debug:
        rmtree = _verbose_rmtree
    else:
        rmtree = shutil.rmtree
    click.secho('Cleaning working tree', bold=True)
    rmtree('inventory', ignore_errors=True)
    rmtree('dependencies', ignore_errors=True)
    rmtree('compiled', ignore_errors=True)
    rmtree('catalog', ignore_errors=True)

def kapitan_compile():
    # TODO: maybe use kapitan.targets.compile_targets directly?
    import shlex, subprocess
    click.secho('Compiling catalog...', bold=True)
    return subprocess.run(shlex.split('kapitan compile --fetch -J .  dependencies --refs-path ./catalog/refs'))

def rm_tree_contents(dir):
    """
    Delete all files in directory `dir`, but do not delete the directory
    itself.
    """
    import os
    dir = P(dir)
    if not dir.is_dir():
        raise ValueError('Expected directory as argument')
    for f in dir.glob('*'):
        if f.name.startswith('.'):
            # pathlib's glob doesn't filter hidden files, skip them here
            continue
        if f.is_dir():
            shutil.rmtree(f)
        else:
            os.unlink(f)
