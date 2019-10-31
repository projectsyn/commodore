import click

from pathlib import Path as P

from commodore.helpers import yaml_load

from .jsonnet import run_jsonnet_filter
from .builtin_filters import run_builtin_filter

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
            for f in filters['filters']:
                # old-style filters are always 'jsonnet'
                if not 'type' in f:
                    click.secho(f"   > [WARN] component uses old-style postprocess filters",
                                fg='yellow')
                    f['type'] = 'jsonnet'
                if f['type'] == 'jsonnet':
                    run_jsonnet_filter(inventory, cn, target, filterdir, f)
                elif f['type'] == 'builtin':
                    run_builtin_filter(inventory, cn, target, f)
                else:
                    click.secho(f"   > [WARN] unknown builtin filter {f['filter']}",
                                fg='yellow')
