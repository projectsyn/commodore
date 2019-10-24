import _jsonnet, json, pathlib, os, click
from ruamel.yaml import YAML

def _yaml_load(file):
    yaml=YAML(typ='safe')
    with open(file, 'r') as f:
        return yaml.load(f)

#  Returns content if worked, None if file not found, or throws an exception
def _try_path(dir, rel):
    if not rel:
        raise RuntimeError('Got invalid filename (empty string).')
    if rel[0] == '/':
        full_path = rel
    else:
        full_path = dir + rel
    if full_path[-1] == '/':
        raise RuntimeError('Attempted to import a directory')

    if not os.path.isfile(full_path):
        return full_path, None
    with open(full_path) as f:
        return full_path, f.read()

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
    search_path = [f"{os.getcwd()}/"]
    return _import_callback_with_searchpath(search_path, dir, rel)

_native_callbacks = {
    'yaml_load': (('file',), _yaml_load),
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
    yaml=YAML()
    yaml.default_flow_style = False
    yaml.indent(mapping=2, sequence=4, offset=2)
    for outobj, outcontents in out_objs.items():
        outpath=pathlib.PurePath('compiled', target, output_path, f"{outobj}.yaml")
        with open(outpath, 'w') as outf:
            yaml.dump(outcontents, outf)

def postprocess_components(inventory, target, components):
    click.secho("Postprocessing...", bold=True)
    for cn, c in components.items():
        if f"components.{cn}" not in inventory["classes"]:
            continue
        repodir = pathlib.PurePath(c.repo.working_tree_dir)
        filterdir = repodir / "postprocess"
        if os.path.isdir(filterdir):
            click.echo(f" > {cn}...")
            filters = _yaml_load(filterdir / "filters.yml")
            for filter in filters['filters']:
                filterpath = filterdir / filter['filter']
                output_path = filter['output_path']
                exec_postprocess_jsonnet(inventory, cn, filterpath, target, output_path)
