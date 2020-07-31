import json

from pathlib import Path as P

import _jsonnet
import click

from commodore import __install_dir__

from .jsonnet import jsonnet_runner


def _builtin_filter_helm_namespace(inv, component, target, path, **kwargs):
    if 'namespace' not in kwargs:
        raise click.ClickException(
            "Builtin filter 'helm_namespace': filter argument 'namespace' is required")
    create_namespace = kwargs.get('create_namespace', 'false')
    exclude_objects = kwargs.get('exclude_objects', [])
    exclude_objects = '|'.join([json.dumps(e) for e in exclude_objects])
    output_dir = P('compiled', target, path)

    # pylint: disable=c-extension-no-member
    jsonnet_runner(inv, component, target, path,
                   _jsonnet.evaluate_file,
                   __install_dir__ / 'filters' / 'helm_namespace.jsonnet',
                   namespace=kwargs['namespace'],
                   create_namespace=create_namespace,
                   exclude_objects=exclude_objects,
                   chart_output_dir=str(output_dir))


_builtin_filters = {
    'helm_namespace': _builtin_filter_helm_namespace,
}


def run_builtin_filter(inv, component, target, f):
    fname = f['filter']
    if fname not in _builtin_filters:
        click.secho(f"   > [ERR ] Unknown builtin filter {fname}", fg='red')
        return
    _builtin_filters[fname](inv, component, target, f['path'], **f['filterargs'])
