from pathlib import Path

import pytest

from commodore.config import Config
from commodore.inventory import render
from commodore.inventory.parameters import InventoryFacts

from test_inventory_parameters import (
    setup_global_repo_dir,
    verify_components,
    GLOBAL_PARAMS,
    DIST_PARAMS,
    CLOUD_REGION_PARAMS,
    CLOUD_REGION_TESTCASES,
)


@pytest.mark.parametrize("distribution", DIST_PARAMS.keys())
@pytest.mark.parametrize("cloud,region", CLOUD_REGION_TESTCASES)
def test_extract_components(tmp_path: Path, distribution: str, cloud: str, region: str):
    global_dir = setup_global_repo_dir(
        tmp_path, GLOBAL_PARAMS, DIST_PARAMS, CLOUD_REGION_PARAMS
    )
    config = Config(tmp_path)

    invfacts = InventoryFacts(global_dir, None, distribution, cloud, region)
    components = render.extract_components(config, invfacts)

    assert set(components.keys()) == set(GLOBAL_PARAMS["components"].keys())
    verify_components(components, distribution, cloud, region)


@pytest.mark.parametrize(
    "invfacts,exception_message",
    [
        (
            lambda g: InventoryFacts(g, None, "x-invalid-dist", None, None),
            "Unknown distribution 'x-invalid-dist' in global defaults",
        ),
        (
            lambda g: InventoryFacts(g, None, None, "x-invalid-cloud", None),
            "Unknown cloud 'x-invalid-cloud' in global defaults",
        ),
        (
            lambda g: InventoryFacts(g, None, None, "x", "x-invalid-region"),
            "Unknown cloud region 'x-invalid-region' for cloud 'x'",
        ),
        (
            lambda g: InventoryFacts(g, None, None, None, "region"),
            "Unable to extract components for cloud region 'region', no cloud name provided.",
        ),
    ],
)
def test_extract_components_valueerror_on_invalid_args(
    tmp_path: Path, invfacts, exception_message: str
):
    global_dir = setup_global_repo_dir(
        tmp_path, GLOBAL_PARAMS, DIST_PARAMS, CLOUD_REGION_PARAMS
    )
    config = Config(tmp_path)

    with pytest.raises(ValueError, match=exception_message):
        render.extract_components(config, invfacts(global_dir))
