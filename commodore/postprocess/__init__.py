import _jsonnet, json, click, os
from pathlib import Path as P

from commodore.helpers import yaml_load, yaml_load_all, yaml_dump, yaml_dump_all

#  Returns content if worked, None if file not found, or throws an exception
def _try_path(dir, rel):
    if not rel:
        raise RuntimeError('Got invalid filename (empty string).')
    if rel[0] == '/':
        full_path = P(rel)
    else:
        full_path = P(dir) / rel
    if full_path.is_dir():
        raise RuntimeError('Attempted to import a directory')

    if not full_path.is_file():
        return full_path.name, None
    with open(full_path) as f:
        return full_path.name, f.read()

def _import_callback_with_searchpath(search, dir, rel):
    full_path, content = _try_path(dir, rel)
    if content:
        return full_path, content
    for p in search:
        full_path, content = _try_path(p, rel)
        if content:
            return full_path, content
    raise RuntimeError('File not found')

def _import_cb(dir, rel):
    # Add current working dir to search path for Jsonnet import callback
    search_path = [P('.').resolve()]
    return _import_callback_with_searchpath(search_path, dir, rel)

_native_callbacks = {
    'yaml_load': (('file',), yaml_load),
    'yaml_load_all': (('file',), yaml_load_all)
}

def exec_postprocess_jsonnet(inv, component, filterfile, target, output_path):
    """
    Expects Kapitan-style jsonnet
    """
    def _inventory():
        return inv
    _native_cb = _native_callbacks
    _native_cb['inventory'] = ((), _inventory)
    output = _jsonnet.evaluate_file(
        str(filterfile),
        import_callback=_import_cb,
        native_callbacks=_native_cb,
        ext_vars={'target': target, 'component': component},
    )
    out_objs = json.loads(output)
    for outobj, outcontents in out_objs.items():
        outpath=P('compiled', target, output_path, f"{outobj}.yaml")
        if not outpath.exists():
            print(f" > {outpath} doesn't exist, creating...")
            os.makedirs(outpath.parent, exist_ok=True)
        if isinstance(outcontents, list):
            yaml_dump_all(outcontents, outpath)
        else:
            yaml_dump(outcontents, outpath)

def postprocess_components(inventory, target, components):
    click.secho('Postprocessing...', bold=True)
    for cn, c in components.items():
        if f"components.{cn}" not in inventory['classes']:
            continue
        repodir = P(c.repo.working_tree_dir)
        filterdir = repodir / 'postprocess'
        if filterdir.is_dir():
            click.echo(f" > {cn}...")
            filters = yaml_load(filterdir / 'filters.yml')
            for filter in filters['filters']:
                filterpath = filterdir / filter['filter']
                output_path = filter['output_path']
                exec_postprocess_jsonnet(inventory, cn, filterpath, target, output_path)
