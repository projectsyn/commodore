from __future__ import annotations

import re
import time

from collections.abc import Iterable
from datetime import timedelta
from pathlib import Path
from typing import Union, Type

import click
import git
import github
import yaml.parser
import yaml.scanner

from github.Repository import Repository

from commodore.config import Config
from commodore.helpers import yaml_load

from commodore.component import Component
from commodore.package import Package

from commodore.dependency_templater import Templater


def sync_dependencies(
    config: Config,
    dependency_list: Path,
    dry_run: bool,
    pr_branch: str,
    pr_label: Iterable[str],
    deptype: Type[Union[Component, Package]],
    templater: Type[Templater],
    pr_batch_size: int = 10,
    pause: timedelta = timedelta(seconds=120),
    depfilter: str = "",
) -> None:
    if not config.github_token:
        raise click.ClickException("Can't continue, missing GitHub API token.")

    deptype_str = deptype.__name__.lower()

    deps = read_dependency_list(dependency_list, depfilter)
    dep_count = len(deps)

    gh = github.Github(config.github_token)
    # Keep track of how many PRs we've created to better avoid running into rate limits
    update_count = 0
    for i, dn in enumerate(deps, start=1):
        click.secho(f"Synchronizing {dn}", bold=True)
        _, dreponame = dn.split("/")
        dname = dreponame.replace(f"{deptype_str}-", "", 1)

        # Clone dependency
        try:
            gr = gh.get_repo(dn)
        except github.UnknownObjectException:
            click.secho(f" > Repository {dn} doesn't exist, skipping...", fg="yellow")
            continue

        if gr.archived:
            click.secho(f" > Repository {dn} is archived, skipping...", fg="yellow")
            continue

        d = deptype.clone(config, gr.clone_url, dname, version=gr.default_branch)

        if not (d.target_dir / ".cruft.json").is_file():
            click.echo(f" > Skipping repo {dn} which doesn't have `.cruft.json`")
            continue

        # Update the dependency
        t = templater.from_existing(config, d.target_dir)
        changed = t.update(
            print_completion_message=False,
            commit=not dry_run,
            ignore_template_commit=True,
        )

        # Create or update PR if there were updates
        comment = render_pr_comment(d)
        create_or_update_pr(d, dn, gr, changed, pr_branch, pr_label, dry_run, comment)
        if changed:
            update_count += 1
        if not dry_run and i < dep_count:
            # Pause processing to avoid running into GitHub secondary rate limits, if
            # we're not in dry run mode, and we've not yet processed the last
            # dependency.
            _maybe_pause(update_count, pr_batch_size, pause)


def read_dependency_list(dependency_list: Path, depfilter: str) -> list[str]:
    try:
        deps = yaml_load(dependency_list)
        if not isinstance(deps, list):
            raise ValueError(f"unexpected type: {type_name(deps)}")
        if depfilter != "":
            f = re.compile(depfilter)
            deps = [d for d in deps if f.search(d)]
        return deps
    except ValueError as e:
        raise click.ClickException(
            f"Expected a list in '{dependency_list}', but got {e}"
        )
    except (yaml.parser.ParserError, yaml.scanner.ScannerError):
        raise click.ClickException(f"Failed to parse YAML in '{dependency_list}'")


def render_pr_comment(d: Union[Component, Package]):
    """Render comment to add to PR if there's `.rej` files in the dependency repo after
    applying the template update."""
    deptype = type_name(d)

    if not d.repo or not d.repo.working_tree_dir:
        raise ValueError(f"{deptype} repo not initialized")

    comment = ""
    rej_files = [
        fname for fname in d.repo.repo.untracked_files if fname.endswith(".rej")
    ]
    if len(rej_files) > 0:
        comment = (
            f"{deptype.capitalize()} update was only partially successful. "
            + "Please check the PR carefully.\n\n"
            + "Rejected patches:\n\n"
        )
        for fname in rej_files:
            with open(d.repo.working_tree_dir / fname, "r", encoding="utf-8") as f:
                comment += "```diff\n" + f.read() + "```\n"

    return comment


def _maybe_pause(update_count: int, pr_batch_size: int, pause: timedelta):
    if update_count > 0 and update_count % pr_batch_size == 0:
        # Pause for 2 minutes after we've created `pr_batch_size` (defaults to 10)
        # PRs, to avoid hitting secondary rate limits for PR creation. No need to
        # consider dependencies for which we're not creating a PR. Additionally,
        # never sleep after processing the last dependency.
        click.echo(
            f" > Created or updated {pr_batch_size} PRs, "
            + f"pausing for {pause.seconds}s to avoid secondary rate limits."
        )
        time.sleep(pause.seconds)


def create_or_update_pr(
    d: Union[Component, Package],
    dn: str,
    gr: Repository,
    changed: bool,
    pr_branch: str,
    pr_label,
    dry_run: bool,
    comment: str,
):
    if dry_run and changed:
        click.secho(f"Would create or update PR for {dn}", bold=True)
    elif changed:
        ensure_branch(d, pr_branch)
        msg = ensure_pr(d, dn, gr, pr_branch, pr_label, comment)
        click.secho(msg, bold=True)
    else:
        dep_type = type_name(d)
        click.secho(f"{dep_type.capitalize()} {dn} already up-to-date", bold=True)


def message_body(c: git.objects.commit.Commit) -> str:
    if isinstance(c.message, bytes):
        msg = str(c.message, encoding="utf-8")
    else:
        msg = c.message
    paragraphs = msg.split("\n\n")
    return "\n\n".join(paragraphs[1:])


def ensure_branch(d: Union[Component, Package], branch_name: str):
    """Create or reset `template-sync` branch pointing to our new template update
    commit."""
    deptype = type_name(d)

    if not d.repo:
        raise ValueError(f"{deptype} repo not initialized")
    r = d.repo.repo
    has_sync_branch = any(h.name == branch_name for h in r.heads)

    if not has_sync_branch:
        r.create_head(branch_name)
    else:
        new_update = r.head.commit
        template_sync = [h for h in r.heads if h.name == branch_name][0]
        template_sync.set_reference(new_update)


def ensure_pr(
    d: Union[Component, Package],
    dn: str,
    gr: Repository,
    branch_name: str,
    pr_labels: Iterable[str],
    comment: str,
) -> str:
    """Create or update template sync PR."""
    deptype = type_name(d)

    if not d.repo:
        raise ValueError(f"{deptype} repo not initialized")

    prs = gr.get_pulls(state="open")
    has_sync_pr = any(pr.head.ref == branch_name for pr in prs)
    cu = "update" if has_sync_pr else "create"

    r = d.repo.repo
    r.remote().push(branch_name, force=True)
    pr_body = message_body(r.head.commit)

    try:
        if not has_sync_pr:
            sync_pr = gr.create_pull(
                f"Update from {deptype} template",
                pr_body,
                gr.default_branch,
                branch_name,
            )
        else:
            sync_pr = [pr for pr in prs if pr.head.ref == branch_name][0]
            sync_pr.edit(body=pr_body)
        sync_pr.add_to_labels(*list(pr_labels))
        if comment != "":
            sync_pr.as_issue().create_comment(comment)
    except github.UnknownObjectException:
        return (
            f"Unable to {cu} PR for {dn}. "
            + "Please make sure your GitHub token has permission 'public_repo'"
        )

    return f"PR for {deptype} {dn} successfully {cu}d"


def type_name(o: object) -> str:
    return type(o).__name__.lower()
