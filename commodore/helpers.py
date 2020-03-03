import json
import shutil
from pathlib import Path as P

import click
import requests
import yaml

# pylint: disable=redefined-builtin
from requests.exceptions import ConnectionError, HTTPError
from url_normalize import url_normalize


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
    pass


def lieutenant_query(api_url, api_token, api_endpoint, api_id):
    try:
        r = requests.get(url_normalize(f"{api_url}/{api_endpoint}/{api_id}"),
                         headers={'Authorization': f"Bearer {api_token}"})
    except ConnectionError as e:
        raise ApiError(f"Unable to connect to Lieutenant at {api_url}") from e
    try:
        resp = json.loads(r.text)
    except json.JSONDecodeError:
        resp = {'message': 'Client error: Unable to parse JSON'}
    try:
        r.raise_for_status()
    except HTTPError as e:
        extra_msg = ''
        if r.status_code >= 400:
            extra_msg = f": {resp['reason']}"
            raise ApiError(f"API returned {r.status_code}. Reason: {extra_msg}") from e
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
    # pylint: disable=import-outside-toplevel
    import shlex
    import subprocess  # nosec
    click.secho('Compiling catalog...', bold=True)
    return subprocess.run(  # nosec
        shlex.split('kapitan compile --fetch -J .  dependencies --refs-path ./catalog/refs'),
        check=True)


def rm_tree_contents(basedir):
    """
    Delete all files in directory `basedir`, but do not delete the directory
    itself.
    """
    # pylint: disable=import-outside-toplevel
    import os
    basedir = P(basedir)
    if not basedir.is_dir():
        raise ValueError('Expected directory as argument')
    for f in basedir.glob('*'):
        if f.name.startswith('.'):
            # pathlib's glob doesn't filter hidden files, skip them here
            continue
        if f.is_dir():
            shutil.rmtree(f)
        else:
            os.unlink(f)
