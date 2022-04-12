from __future__ import annotations

import shutil
import tempfile

from pathlib import Path

import click

from commodore.config import Config

from .parameters import ClassNotFound, InventoryFactory, InventoryFacts


def _cleanup_work_dir(cfg: Config, work_dir: Path):
    if not cfg.debug:
        # Clean up work dir if we're not in debug mode
        shutil.rmtree(work_dir)


def extract_components(
    cfg: Config, invfacts: InventoryFacts
) -> dict[str, dict[str, str]]:
    if cfg.debug:
        click.echo(
            f"Called with: global_config={invfacts.global_config} "
            + f"tenant_config={invfacts.tenant_config} "
            + f"extra_classes={invfacts.extra_classes} "
            + f"allow_missing_classes={invfacts.allow_missing_classes}."
        )

    global_dir = Path(invfacts.global_config).resolve().absolute()
    tenant_dir = None
    if invfacts.tenant_config:
        tenant_dir = Path(invfacts.tenant_config).resolve().absolute()

    work_dir = Path(tempfile.mkdtemp(prefix="commodore-reclass-")).resolve()

    if global_dir.is_dir() and (not tenant_dir or tenant_dir.is_dir()):
        invfactory = InventoryFactory.from_repo_dirs(
            work_dir, global_dir, tenant_dir, invfacts
        )
    else:
        _cleanup_work_dir(cfg, work_dir)
        raise NotImplementedError("Cloning global or tenant repo not yet implemented")

    try:
        inv = invfactory.reclass(invfacts)
        components = inv.parameters("components")
    except ClassNotFound as e:
        _cleanup_work_dir(cfg, work_dir)
        raise ValueError(
            "Unable to render inventory with `--no-allow-missing-classes`. "
            + f"Class '{e.name}' not found. "
            + "Verify the provided values or allow missing classes."
        ) from e

    _cleanup_work_dir(cfg, work_dir)

    return components
