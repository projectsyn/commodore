import _jsonnet, click, re

from pathlib import Path as P

from .jsonnet import jsonnet_runner

def _builtin_filter_helm_namespace(inv, component, target, path, **kwargs):
    if 'namespace' not in kwargs:
        raise click.ClickException("Builtin filter 'helm_namespace': filter argument 'namespace' is required")
    if 'create_namespace' in kwargs:
        create_namespace = kwargs['create_namespace']
    else:
        create_namespace = "false"
    output_dir = P('compiled', target, path)

    jsonnet_runner(inv, component, target, path,
            _jsonnet.evaluate_file, P('filters', 'helm_namespace.jsonnet'),
            namespace = kwargs['namespace'], create_namespace = create_namespace, chart_output_dir=str(output_dir))

_builtin_filters = {
    'helm_namespace': _builtin_filter_helm_namespace,
}

class InventoryError(Exception):
    pass

def _resolve_var(inv, m):
    var = m.group(1)
    invpath = var.split(':')
    val = inv['parameters']
    for elem in invpath:
        val = val.get(elem, None)
        if val is None:
            raise InventoryError(f"Unable to resolve inventory reference {var}")
    return val

INV_REF = re.compile('\$\{([^}]+)\}')
def _resolve_inventory_vars(inv, args):
    resolved = {}
    for k, v in args.items():
        if isinstance(v, str):
            resolved[k] = INV_REF.sub(lambda m: _resolve_var(inv, m), v)
        else:
            resolved[k] = v
    return resolved

def run_builtin_filter(inv, component, target, f):
    fname = f['filter']
    if fname not in _builtin_filters:
        click.secho(f"   > [ERR ] Unknown builtin filter {fname}", fg='red')
        return
    try:
        filterargs = _resolve_inventory_vars(inv, f['filterargs'])
    except InventoryError as e:
        raise click.ClickException(f"Failure in builtin filter: {e}") from e
    _builtin_filters[fname](inv, component, target, f['path'], **filterargs)

