import shutil
import tempfile

from pathlib import Path
from typing import Dict

import click

from commodore.config import Config

from .parameters import InventoryFactory
from .parameters import InventoryFacts


def extract_components(
    cfg: Config, invfacts: InventoryFacts
) -> Dict[str, Dict[str, str]]:
    if cfg.debug:
        click.echo(
            f"Called with: global_config={invfacts.global_config} "
            + f"tenant_config={invfacts.tenant_config} "
            + f"distribution={invfacts.distribution} "
            + f"cloud={invfacts.cloud} region={invfacts.region}"
        )

    global_dir = Path(invfacts.global_config).resolve().absolute()
    work_dir = Path(tempfile.mkdtemp(prefix="renovate-reclass-")).resolve()

    if global_dir.is_dir():
        invfactory = InventoryFactory.from_repo_dir(work_dir, global_dir)
    else:
        raise NotImplementedError("Cloning the inventory first not yet implemented")

    if invfacts.distribution and invfacts.distribution not in invfactory.distributions:
        raise ValueError(
            f"Unknown distribution '{invfacts.distribution}' in global defaults {global_dir}"
        )

    if invfacts.cloud and invfacts.cloud not in invfactory.clouds:
        raise ValueError(
            f"Unknown distribution '{invfacts.distribution}' in global defaults {global_dir}"
        )

    if invfacts.region and not invfacts.cloud:
        raise ValueError(
            f"Unable to extract components for cloud region {invfacts.region}, no cloud name provided."
        )

    if (
        invfacts.region
        and invfacts.region not in invfactory.cloud_regions[invfacts.cloud]
    ):
        raise ValueError(
            f"Unknown cloud region '{invfacts.region}' for cloud '{invfacts.cloud}'"
        )

    inv = invfactory.reclass(invfacts)
    components = inv.parameters("components")

    if not cfg.debug:
        # Clean up work dir if we're not in debug mode
        shutil.rmtree(work_dir)

    return components
