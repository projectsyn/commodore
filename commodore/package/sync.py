from __future__ import annotations

import random
import time

from pathlib import Path

import click
import git
import github
import yaml.parser

from github.Repository import Repository

from commodore.config import Config
from commodore.helpers import yaml_load

from . import Package
from .template import PackageTemplater


def sync_packages(config: Config, package_list: Path, dry_run: bool) -> None:
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
    for pn in pkgs:
        click.secho(f"Synchronizing {pn}", bold=True)
        porg, preponame = pn.split("/")
        pname = preponame.replace("package-", "", 1)

        # Clone package
        gr = gh.get_repo(pn)
        p = Package.clone(config, gr.clone_url, pname, version="master")

        if not (p.target_dir / ".cruft.json").is_file():
            click.echo(f" > Skipping repo {pn} which doesn't have `.cruft.json`")
            continue

        # Run `package update`
        t = PackageTemplater.from_existing(config, p.target_dir)
        changed = t.update()

        # Create or update PR if there were updates
        if changed:
            ensure_branch(p)
            ensure_pr(p, pn, gr, dry_run)

            # sleep for 1-2 seconds to avoid hitting secondary rate-limits for PR
            # creation. No need to sleep if we're not creating a PR.
            backoff = 1.0 + random.random()  # nosec
            time.sleep(backoff)


def message_body(c: git.objects.commit.Commit) -> str:
    if isinstance(c.message, bytes):
        msg = str(c.message, encoding="utf-8")
    else:
        msg = c.message
    paragraphs = msg.split("\n\n")
    return "\n\n".join(paragraphs[1:])


def ensure_branch(p: Package):
    """Create or reset `template-sync` branch pointing to our new template update
    commit."""
    if not p.repo:
        raise ValueError("package repo not initialized")
    r = p.repo.repo
    has_sync_branch = any(h.name == "template-sync" for h in r.heads)

    if not has_sync_branch:
        r.create_head("template-sync")
    else:
        new_update = r.head.commit
        template_sync = [h for h in r.heads if h.name == "template-sync"][0]
        template_sync.set_reference(new_update)


def ensure_pr(p: Package, pn: str, gr: Repository, dry_run: bool):
    """Create or update template sync PR."""
    if not p.repo:
        raise ValueError("package repo not initialized")

    prs = gr.get_pulls(state="open")
    has_sync_pr = any(pr.head.ref == "template-sync" for pr in prs)

    if dry_run:
        cu = "update" if has_sync_pr else "create"
        click.echo(f"Would {cu} PR for {pn}")
        return

    r = p.repo.repo
    r.remote().push("template-sync", force=True)
    pr_body = message_body(r.head.commit)

    if not has_sync_pr:
        pr = gr.create_pull(
            "Update from package template",
            pr_body,
            "master",
            "template-sync",
        )
        pr.add_to_labels("template-sync")
    else:
        sync_pr = [pr for pr in prs if pr.head.ref == "template-sync"][0]
        sync_pr.edit(body=pr_body)
