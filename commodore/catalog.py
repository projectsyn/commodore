from __future__ import annotations

import difflib
import shutil
import time
import textwrap

from collections.abc import Iterable
from pathlib import Path as P

import click
import yaml
import json

from .component import Component
from .gitrepo import GitRepo, GitCommandError
from .helpers import (
    ApiError,
    rm_tree_contents,
    lieutenant_query,
    sliding_window,
    IndentedListDumper,
)
from .cluster import Cluster
from .config import Config, Migration
from .k8sobject import K8sObject


def fetch_catalog(config: Config, cluster: Cluster) -> GitRepo:
    click.secho("Updating cluster catalog...", bold=True)
    repo_url = cluster.catalog_repo_url
    if config.debug:
        click.echo(f" > Cloning cluster catalog {repo_url}")
    return GitRepo.clone(repo_url, config.catalog_dir, config)


def _pretty_print_component_commit(name, component: Component) -> str:
    short_sha = component.repo.head_short_sha
    return f" * {name}: {component.version} ({short_sha})"


def _pretty_print_config_commit(name, repo: GitRepo) -> str:
    short_sha = repo.head_short_sha
    return f" * {name}: {short_sha}"


def _render_catalog_commit_msg(cfg) -> str:
    # pylint: disable=import-outside-toplevel
    import datetime

    now = datetime.datetime.now().isoformat(timespec="milliseconds")

    component_commits = [
        _pretty_print_component_commit(cn, c) for cn, c in cfg.get_components().items()
    ]
    component_commits_str = "\n".join(component_commits)

    config_commits = [
        _pretty_print_config_commit(c, r) for c, r in cfg.get_configs().items()
    ]
    config_commits_str = "\n".join(config_commits)

    return f"""Automated catalog update from Commodore

Component commits:
{component_commits_str}

Configuration commits:
{config_commits_str}

Compilation timestamp: {now}
"""


def clean_catalog(repo: GitRepo):
    if repo.working_tree_dir is None:
        raise click.ClickException("Catalog repo has no working tree")

    catalogdir = P(repo.working_tree_dir, "manifests")
    click.secho("Cleaning catalog repository...", bold=True)
    # delete everything in catalog
    if catalogdir.is_dir():
        rm_tree_contents(catalogdir)
    else:
        click.echo(
            f" > Skipping cleaning, catalog directory {catalogdir} doesn't exist"
        )


def _push_catalog(cfg: Config, repo: GitRepo, commit_message: str):
    """Push catalog to catalog repo if conditions to allow push are met.

    Conditions to allow pushing are:
    * Commodore doesn't run in local mode
    * User has requested pushing with `--push`

    Ask user to confirm push if `--interactive` is specified
    """
    if cfg.local:
        repo.reset(working_tree=False)
        click.echo(" > Skipping commit+push to catalog in local mode...")
        return

    if cfg.interactive and cfg.push:
        cfg.push = click.confirm(" > Should the push be done?")

    if cfg.push:
        click.echo(" > Commiting changes...")
        repo.commit(commit_message)
        click.echo(" > Pushing catalog to remote...")
        try:
            pushinfos = repo.push()
        except GitCommandError as e:
            raise click.ClickException(
                "Failed to push to the catalog repository: "
                + f"Git exited with status code {e.status}"
            ) from e
        for pi in pushinfos:
            # Any error has pi.ERROR set in the `flags` bitmask
            # We just forward the summary from the first pushinfo which has the error
            # flag set.
            summary = pi.summary.strip()
            if (pi.flags & pi.ERROR) != 0:
                raise click.ClickException(
                    f"Failed to push to the catalog repository: {summary}"
                )
    else:
        click.echo(" > Skipping commit+push to catalog...")
        click.echo(" > Use flag --push to commit and push the catalog repo")
        click.echo(" > Add flag --interactive to show the diff and decide on the push")


def _is_semantic_diff_kapitan_029_030(win: tuple[str, str]) -> bool:
    """
    Returns True if a pair of lines of a diff which is already sorted
    by K8s object indicates that this diff contains a semantic change
    when migrating from  Kapitan 0.29 to 0.30.

    The function expects pairs of diff lines as input.

    The function treats the following diffs as non-semantic:
    * Change of "app.kubernetes.io/managed-by: Tiller" to
      "app.kubernetes.io/managed-by: Helm"
    * Change of "heritage: Tiller" to "heritage: Helm"
    * `null` objects not emitted in multi-object YAML documents anymore
    """
    line_a, line_b = map(str.rstrip, win)

    # Ignore context and metadata lines:
    if (
        # We don't use line_a/line_b here, as it's possible that the leading space of a
        # context line gets stripped if the line is empty.
        win[0].startswith(" ")
        or win[1].startswith(" ")
        or line_a.startswith("@@")
        or line_b.startswith("@@")
    ):
        return False

    # Ignore changes where we don't emit a null object preceded or followed
    # by a stream separator anymore
    if line_a == "-null" and line_b in ("----", "---- null"):
        return False
    if line_a == "---- null" and line_b in ("----", "---- null"):
        return False

    # Ignore changes which are only about Tiller -> Helm as object manager
    if line_a.startswith("-") and line_b.startswith("+"):
        if line_a.endswith("app.kubernetes.io/managed-by: Tiller") and line_b.endswith(
            "app.kubernetes.io/managed-by: Helm"
        ):
            return False
        if line_a.endswith("heritage: Tiller") and line_b.endswith("heritage: Helm"):
            return False

    # Don't ignore any other diffs
    return True


def _kapitan_029_030_difffunc(
    before_text: str, after_text: str, fromfile: str = "", tofile: str = ""
) -> tuple[Iterable[str], bool]:

    diff_lines, _ = _ignore_yaml_formatting_difffunc(
        before_text, after_text, fromfile, tofile
    )

    suppress_diff = not any(
        _is_semantic_diff_kapitan_029_030(win)
        for win in sliding_window(diff_lines[2:], 2)
    )

    return diff_lines, suppress_diff


def _ignore_yaml_formatting_difffunc(
    before_text: str, after_text: str, fromfile: str = "", tofile: str = ""
) -> tuple[list[str], bool]:

    before_objs = sorted(yaml.safe_load_all(before_text), key=K8sObject)
    before_sorted_lines = yaml.dump_all(before_objs, Dumper=IndentedListDumper).split(
        "\n"
    )

    after_objs = sorted(yaml.safe_load_all(after_text), key=K8sObject)
    after_sorted_lines = yaml.dump_all(after_objs, Dumper=IndentedListDumper).split(
        "\n"
    )

    diff = difflib.unified_diff(
        before_sorted_lines,
        after_sorted_lines,
        lineterm="",
        fromfile=fromfile,
        tofile=tofile,
    )

    diff_lines = list(diff)
    return diff_lines, len(diff_lines) == 0


def update_catalog(cfg: Config, targets: Iterable[str], repo: GitRepo):
    if repo.working_tree_dir is None:
        raise click.ClickException("Catalog repo has no working tree")

    click.secho("Updating catalog repository...", bold=True)

    catalogdir = P(repo.working_tree_dir, "manifests")
    for target_name in targets:
        shutil.copytree(
            cfg.inventory.output_dir / target_name, catalogdir, dirs_exist_ok=True
        )

    start = time.time()
    if cfg.migration == Migration.KAP_029_030:
        click.echo(" > Smart diffing started... (this can take a while)")
        difftext, changed = repo.stage_all(diff_func=_kapitan_029_030_difffunc)
    elif cfg.migration == Migration.IGNORE_YAML_FORMATTING:
        click.echo(" > Smart diffing started... (this can take a while)")
        difftext, changed = repo.stage_all(diff_func=_ignore_yaml_formatting_difffunc)
    else:
        difftext, changed = repo.stage_all()
    elapsed = time.time() - start

    if changed:
        indented = textwrap.indent(difftext, "     ")
        message = f" > Changes:\n{indented}"
        if cfg.migration:
            message += f"\n > Smart diffing took {elapsed:.2f}s"
    else:
        message = " > No changes."
    click.echo(message)

    commit_message = _render_catalog_commit_msg(cfg)
    if cfg.debug:
        click.echo(" > Commit message will be")
        click.echo(textwrap.indent(commit_message, "   "))
    if changed:
        _push_catalog(cfg, repo, commit_message)
    else:
        click.echo(" > Skipping commit+push to catalog...")


def catalog_list(cfg, out: str, sort_by: str = "id", tenant: str = ""):
    params = {"sort_by": sort_by}
    if tenant != "":
        params["tenant"] = tenant
    try:
        clusters = lieutenant_query(
            cfg.api_url, cfg.api_token, "clusters", "", params=params
        )
    except ApiError as e:
        raise click.ClickException(f"While listing clusters on Lieutenant: {e}") from e
    if out == "yaml" or out == "yml":
        click.echo(yaml.safe_dump(clusters))
    elif out == "json":
        click.echo(json.dumps(clusters, indent=2))
    elif out == "id":
        _print_clusters_id(clusters)
    else:
        _print_clusters_pretty(clusters)


def _print_clusters_id(clusters):
    for cluster in clusters:
        click.echo(cluster["id"])


def _print_clusters_pretty(clusters):
    columns = {
        "ID": "id",
        "DISPLAY NAME": "displayName",
        "TENANT": "tenant",
    }
    padding = 2 * " "

    widths = {}
    for header in columns:
        widths[header] = len(columns[header] + padding)

    for cluster in clusters:
        for header, path in columns.items():
            widths[header] = max(widths[header], len(cluster.get(path, "") + padding))

    fmtstr = len(widths) * "{:<%d}" % tuple(widths.values())
    click.echo(fmtstr.format(*columns))
    for cluster in clusters:
        click.echo(fmtstr.format(*[cluster.get(path) for path in columns.values()]))
