import shutil
import tempfile

from pathlib import Path
from typing import Dict

import click

from commodore.config import Config

from .parameters import ClassNotFound, InventoryFactory, InventoryFacts


def extract_components(
    cfg: Config, invfacts: InventoryFacts
) -> Dict[str, Dict[str, str]]:
    if cfg.debug:
        click.echo(
            f"Called with: global_config={invfacts.global_config} "
            + f"tenant_config={invfacts.tenant_config} "
            + f"extra_classes={invfacts.extra_classes} "
            + f"allow_missing_classes={invfacts.allow_missing_classes}."
        )

    global_dir = Path(invfacts.global_config).resolve().absolute()
    if invfacts.tenant_config:
        raise NotImplementedError(
            "Extracting component versions from tenant config not yet implemented"
        )
    work_dir = Path(tempfile.mkdtemp(prefix="renovate-reclass-")).resolve()

    if global_dir.is_dir():
        invfactory = InventoryFactory.from_repo_dir(work_dir, global_dir, invfacts)
    else:
        raise NotImplementedError("Cloning the inventory first not yet implemented")

    try:
        inv = invfactory.reclass(invfacts)
        components = inv.parameters("components")
    except ClassNotFound as e:
        print(e)
        raise ValueError(
            "Unable to render inventory with `--no-allow-missing-classes`. "
            + f"Class '{e.name}' not found. "
            + "Verify the provided values or allow missing classes."
        ) from e

    if not cfg.debug:
        # Clean up work dir if we're not in debug mode
        shutil.rmtree(work_dir)

    return components
