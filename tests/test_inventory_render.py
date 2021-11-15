from pathlib import Path

import pytest

from commodore.config import Config
from commodore.inventory import render

from test_inventory_parameters import (
    setup_global_repo_dir,
    create_inventory_facts,
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
    invfacts = create_inventory_facts(tmp_path, global_dir, distribution, cloud, region)
    components = render.extract_components(config, invfacts)

    assert set(components.keys()) == set(GLOBAL_PARAMS["components"].keys())
    verify_components(components, distribution, cloud, region)


@pytest.mark.parametrize(
    "invfacts,expected_error_msg",
    [
        (
            lambda t, g: create_inventory_facts(
                t, g, "x-invalid-dist", None, None, False
            ),
            "Class 'global.distribution.x-invalid-dist' not found.",
        ),
        (
            lambda t, g: create_inventory_facts(
                t, g, "a", "x-invalid-cloud", None, False
            ),
            "Class 'global.cloud.x-invalid-cloud' not found.",
        ),
        (
            lambda t, g: create_inventory_facts(
                t, g, "a", "y", "x-invalid-region", False
            ),
            "Class 'global.cloud.y.x-invalid-region' not found.",
        ),
    ],
)
def test_extract_components_valueerror_on_invalid_args(
    tmp_path: Path, invfacts, expected_error_msg
):
    global_dir = setup_global_repo_dir(
        tmp_path, GLOBAL_PARAMS, DIST_PARAMS, CLOUD_REGION_PARAMS
    )
    config = Config(tmp_path)

    with pytest.raises(
        ValueError,
        match="Unable to render inventory with `--no-allow-missing-classes`. "
        + f"{expected_error_msg} "
        + "Verify the provided values or allow missing classes.",
    ):
        render.extract_components(config, invfacts(tmp_path, global_dir))
