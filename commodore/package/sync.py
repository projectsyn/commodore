from __future__ import annotations

import random
import time

from pathlib import Path
from typing import Iterable, Optional

import click
import git
import github
import yaml.parser

from github.Repository import Repository

from commodore.config import Config
from commodore.helpers import yaml_load

from . import Package
from .template import PackageTemplater


def sync_packages(
    config: Config,
    package_list: Path,
    dry_run: bool,
    pr_branch: str,
    pr_label: Iterable[str],
) -> None:
    if not config.github_token:
        raise click.ClickException("Can't continue, missing GitHub API token.")

    try:
        pkgs = yaml_load(package_list)
        if not isinstance(pkgs, list):
            typ = type(pkgs)
            raise ValueError(f"unexpected type: {typ}")
    except ValueError as e:
        raise click.ClickException(f"Expected a list in '{package_list}', but got {e}")
    except (yaml.parser.ParserError, yaml.scanner.ScannerError):
        raise click.ClickException(f"Failed to parse YAML in '{package_list}'")

    gh = github.Github(config.github_token)
    pkg_count = len(pkgs)
    for i, pn in enumerate(pkgs, start=1):
        click.secho(f"Synchronizing {pn}", bold=True)
        porg, preponame = pn.split("/")
        pname = preponame.replace("package-", "", 1)

        # Clone package
        try:
            gr = gh.get_repo(pn)
        except github.UnknownObjectException:
            click.secho(f" > Repository {pn} doesn't exist, skipping...", fg="yellow")
            continue
        p = Package.clone(config, gr.clone_url, pname, version=gr.default_branch)

        if not (p.target_dir / ".cruft.json").is_file():
            click.echo(f" > Skipping repo {pn} which doesn't have `.cruft.json`")
            continue

        # Run `package update`
        t = PackageTemplater.from_existing(config, p.target_dir)
        changed = t.update(print_completion_message=False)

        # Create or update PR if there were updates
        if changed:
            ensure_branch(p, pr_branch)
            cu = ensure_pr(p, pn, gr, dry_run, pr_branch, pr_label)
            click.secho(f"PR for package {pn} successfully {cu}", bold=True)

            if i < pkg_count:
                # except when processing the last package in the list, sleep for 1-2
                # seconds to avoid hitting secondary rate-limits for PR creation. No
                # need to sleep if we're not creating a PR.
                # Without the #nosec annotations bandit warns (correctly) that
                # `random.random()` generates weak random numbers, but since the quality
                # of the randomness doesn't matter here, we don't need to use a more
                # expensive RNG.
                backoff = 1.0 + random.random()  # nosec
                time.sleep(backoff)
        else:
            click.secho(f"Package {pn} already up-to-date", bold=True)


def message_body(c: git.objects.commit.Commit) -> str:
    if isinstance(c.message, bytes):
        msg = str(c.message, encoding="utf-8")
    else:
        msg = c.message
    paragraphs = msg.split("\n\n")
    return "\n\n".join(paragraphs[1:])


def ensure_branch(p: Package, branch_name: str):
    """Create or reset `template-sync` branch pointing to our new template update
    commit."""
    if not p.repo:
        raise ValueError("package repo not initialized")
    r = p.repo.repo
    has_sync_branch = any(h.name == branch_name for h in r.heads)

    if not has_sync_branch:
        r.create_head(branch_name)
    else:
        new_update = r.head.commit
        template_sync = [h for h in r.heads if h.name == branch_name][0]
        template_sync.set_reference(new_update)


def ensure_pr(
    p: Package,
    pn: str,
    gr: Repository,
    dry_run: bool,
    branch_name: str,
    pr_labels: Iterable[str],
) -> Optional[str]:
    """Create or update template sync PR."""
    if not p.repo:
        raise ValueError("package repo not initialized")

    prs = gr.get_pulls(state="open")
    has_sync_pr = any(pr.head.ref == branch_name for pr in prs)

    cu = "update" if has_sync_pr else "create"
    if dry_run:
        click.echo(f"Would {cu} PR for {pn}")
        return None

    r = p.repo.repo
    r.remote().push(branch_name, force=True)
    pr_body = message_body(r.head.commit)

    try:
        if not has_sync_pr:
            sync_pr = gr.create_pull(
                "Update from package template",
                pr_body,
                gr.default_branch,
                branch_name,
            )
        else:
            sync_pr = [pr for pr in prs if pr.head.ref == branch_name][0]
            sync_pr.edit(body=pr_body)
        sync_pr.add_to_labels(*list(pr_labels))
    except github.UnknownObjectException:
        click.echo(
            f"Unable to {cu} PR for {pn}. "
            + "Please make sure your GitHub token has permission 'public_repo'"
        )
        return None

    return f"{cu}d"
