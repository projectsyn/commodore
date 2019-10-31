import click

from pathlib import Path as P

from commodore.helpers import yaml_load

from .jsonnet import exec_postprocess_jsonnet

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
