from __future__ import annotations

import os
import pytest
import random
from pathlib import Path
from typing import Optional

from commodore.inventory import parameters
from commodore.helpers import yaml_dump


GLOBAL_PARAMS = {
    "components": {
        "tc1": {
            "url": "tc1",
            "version": "gp",
        },
        "tc2": {
            "url": "tc2",
            "version": "gp",
        },
        "tc3": {
            "url": "tc3",
            "version": "gp",
        },
        "tc4": {
            "url": "tc4",
            "version": "gp",
        },
        "tc5": {
            "url": "tc5",
            "version": "gp",
        },
    }
}

DIST_PARAMS = {
    "a": {
        "components": {
            "tc1": {"version": "a_version"},
        },
    },
    "b": {
        "components": {
            "tc2": {"url": "b_url"},
        },
    },
    "c": {"other_key": {}},
    "d": {"test": "testing"},
    # Test that multi-instance related params work correctly
    "e": {"namespace": "${_instance}"},
}

CLOUD_REGION_PARAMS = {
    "x": {
        "components": {
            "tc1": {"version": "x_version"},
        },
    },
    "y": [
        (
            "params",
            {
                "components": {
                    "tc1": {"url": "y_params_url", "version": "y_params_version"},
                }
            },
        ),
        ("m", {"components": {"tc4": {"url": "y_m_url"}}}),
        ("n", {"components": {"tc4": {"version": "y_n_version"}}}),
        ("o", {}),
    ],
    "z": [("a", {})],
}

# Generate a list of tuples (cloud, region) from the CLOUD_REGION_PARAMS map, this
# allows us to parametrize the cloud region reclass test in such a way that it only
# tests valid combinations of cloud and region.
CLOUD_REGION_TESTCASES = [
    (cloud, region[0])
    for cloud, regions in CLOUD_REGION_PARAMS.items()
    for region in regions
    if isinstance(regions, list)
    if region[0] != "params"
]

CLUSTER_PARAMS = {
    "common": {
        "components": {
            "tc3": {"url": "cluster_common_url", "version": "cluster_common_version"}
        }
    },
    "c1": {},
    "c2": {"components": {"tc1": {"url": "c2_url"}, "tc2": {"version": "c2_version"}}},
    "c3": {"components": {"tc3": {"url": "c3_url"}}},
}


def setup_global_repo_dir(
    tmp_path: Path, global_params, distparams, cloud_region_params
) -> Path:
    global_path = tmp_path / "global-defaults"
    os.makedirs(global_path)
    os.makedirs(global_path / "distribution", exist_ok=True)
    os.makedirs(global_path / "cloud", exist_ok=True)
    ext = [".yml", ".yaml"]
    for distribution, params in distparams.items():
        # randomize extensions for distribution classes
        fext = random.choice(ext)
        yaml_dump(
            {"parameters": params},
            global_path / "distribution" / f"{distribution}{fext}",
        )
    for cloud, params in cloud_region_params.items():
        if isinstance(params, dict):
            yaml_dump({"parameters": params}, global_path / "cloud" / f"{cloud}.yml")
        else:
            assert isinstance(params, list)
            os.makedirs(global_path / "cloud" / cloud, exist_ok=True)
            rparams = {}
            for region, params in params:
                if region == "params":
                    rparams = params
                    continue
                yaml_dump(
                    {"parameters": params},
                    global_path / "cloud" / cloud / f"{region}.yml",
                )
            # Write cloud-level params
            yaml_dump(
                {"parameters": rparams},
                global_path / "cloud" / cloud / "params.yml",
            )
            # Configure cloud region hierarchy
            yaml_dump(
                {
                    "classes": [
                        f"global.cloud.{cloud}.params",
                        f"global.cloud.{cloud}.${{facts:region}}",
                    ],
                },
                global_path / "cloud" / f"{cloud}.yml",
            )

    # Write global params
    yaml_dump(
        {"parameters": global_params},
        global_path / "params.yml",
    )

    # Write hierarchy config
    yaml_dump(
        {
            "classes": [
                "global.params",
                "global.distribution.${facts:distribution}",
                "global.cloud.${facts:cloud}",
                "${cluster:tenant}.${cluster:name}",
            ]
        },
        global_path / "commodore.yml",
    )

    return global_path


def setup_tenant_repo_dir(tmp_path: Path, tenant_params) -> Path:
    tenant_path = tmp_path / "tenant-config"
    os.makedirs(tenant_path)

    for cluster_id, cluster_params in tenant_params.items():
        classes = []
        if cluster_id != "common":
            classes.append(".common")
        yaml_dump(
            {
                "classes": classes,
                "parameters": cluster_params,
            },
            tenant_path / f"{cluster_id}.yml",
        )

    return tenant_path


def extract_cloud_region_params(cloud: str, region: str):
    cparams = None
    rparams = None
    crp = CLOUD_REGION_PARAMS[cloud]
    if isinstance(crp, dict):
        return crp, {}

    assert isinstance(crp, list)
    for cr, params in crp:
        if cr == region:
            rparams = params
        if cr == "params":
            cparams = params
    if not cparams:
        cparams = {}
    if not rparams:
        rparams = {}

    return cparams, rparams


def _extract_component(params: dict, cn: str):
    return params.get("components", {}).get(cn, {})


def get_component(
    distribution: Optional[str],
    cloud: Optional[str],
    region: Optional[str],
    cluster_id: Optional[str],
    cn: str,
):
    if cloud:
        cparams, rparams = extract_cloud_region_params(cloud, region)
    else:
        cparams = {}
        rparams = {}

    if region:
        rc = _extract_component(rparams, cn)
    else:
        rc = {}

    if cloud:
        cc = _extract_component(cparams, cn)
    else:
        cc = {}

    if distribution:
        dparams = DIST_PARAMS[distribution]
        dc = _extract_component(dparams, cn)
    else:
        dc = {}

    if cluster_id:
        tenantc = _extract_component(CLUSTER_PARAMS["common"], cn)
        clusterc = _extract_component(CLUSTER_PARAMS[cluster_id], cn)
    else:
        tenantc = {}
        clusterc = {}

    curl = clusterc.get(
        "url", tenantc.get("url", rc.get("url", cc.get("url", dc.get("url", cn))))
    )
    cver = clusterc.get(
        "version",
        tenantc.get(
            "version", rc.get("version", cc.get("version", dc.get("version", "gp")))
        ),
    )

    return {
        "url": curl,
        "version": cver,
    }


def verify_components(
    components: dict[str, dict[str, str]],
    distribution: str,
    cloud: str,
    region: str,
    cluster_id: Optional[str] = None,
):
    for cn, c in components.items():
        ec = get_component(distribution, cloud, region, cluster_id, cn)
        assert c["url"] == ec["url"]
        assert c["version"] == ec["version"]


def create_inventory_facts(
    tmp_path: Path,
    global_config: Path,
    tenant_config: Optional[Path],
    distribution: Optional[str],
    cloud: Optional[str],
    region: Optional[str],
    cluster_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    allow_missing_classes: Optional[bool] = True,
) -> parameters.InventoryFacts:
    params = {"parameters": {"facts": {}, "cluster": {}}}
    if distribution:
        params["parameters"]["facts"]["distribution"] = distribution
    if cloud:
        params["parameters"]["facts"]["cloud"] = cloud
    if region:
        params["parameters"]["facts"]["region"] = region
    if cluster_id:
        params["parameters"]["cluster"]["name"] = cluster_id
        params["parameters"]["cluster"]["tenant"] = tenant_id

    values = tmp_path / "values.yaml"
    yaml_dump(params, values)

    return parameters.InventoryFacts(
        global_config, tenant_config, [values], allow_missing_classes
    )


def test_invfacts_tenant_id(tmp_path: Path):
    value_files = {
        "a.yml": {"parameters": {"cluster": {"tenant": "t-qux"}}},
        "b.yml": {},
        "c.yml": {"parameters": {"cluster": {"tenant": "mytenant"}}},
    }
    expected_tenant_id = [parameters.FAKE_TENANT_ID, "t-qux", "t-qux", "mytenant"]

    for fn, fc in value_files.items():
        yaml_dump(fc, tmp_path / fn)

    for s in range(len(value_files) + 1):
        invfacts = parameters.InventoryFacts(
            None, None, [tmp_path / fn for fn in list(value_files.keys())[:s]], True
        )

        assert invfacts.tenant_id == expected_tenant_id[s]


def test_invfacts_cluster_id(tmp_path: Path):
    value_files = {
        "a.yml": {"parameters": {"cluster": {"name": "c-baz"}}},
        "b.yml": {},
        "c.yml": {"parameters": {"cluster": {"name": "mycluster"}}},
    }
    expected_cluster_id = [parameters.FAKE_CLUSTER_ID, "c-baz", "c-baz", "mycluster"]

    for fn, fc in value_files.items():
        yaml_dump(fc, tmp_path / fn)

    for s in range(len(value_files) + 1):
        invfacts = parameters.InventoryFacts(
            None, None, [tmp_path / fn for fn in list(value_files.keys())[:s]], True
        )

        assert invfacts.cluster_id == expected_cluster_id[s]


def test_inventoryfactory_find_values(tmp_path: Path):
    distributions = {"a": {}, "b": {}, "c": {}, "d": {}}
    cloud_regions = {
        "x": {},
        "y": [("params", {}), ("m", {}), ("n", {}), ("o", {})],
        "z": [("a", {})],
    }
    expected_regions = {
        "x": [],
        "y": ["m", "n", "o"],
        "z": ["a"],
    }
    global_dir = setup_global_repo_dir(tmp_path, {}, distributions, cloud_regions)

    invfactory = parameters.InventoryFactory(
        work_dir=tmp_path, global_dir=global_dir, tenant_dir=None
    )

    assert set(invfactory.distributions) == set(distributions.keys())
    assert set(invfactory.clouds) == set(cloud_regions.keys())
    for cloud in cloud_regions.keys():
        assert set(invfactory.cloud_regions[cloud]) == set(expected_regions[cloud])


def test_inventoryfactory_from_dirs(tmp_path: Path):
    distributions = {"a": {}, "b": {}, "c": {}, "d": {}}
    cloud_regions = {
        "x": {},
        "y": [("params", {}), ("m", {}), ("n", {}), ("o", {})],
        "z": [("a", {})],
    }
    global_dir = setup_global_repo_dir(tmp_path, {}, distributions, cloud_regions)
    invfacts = create_inventory_facts(tmp_path, global_dir, None, None, None, None)

    invfactory = parameters.InventoryFactory.from_repo_dirs(
        tmp_path, global_dir, None, invfacts
    )

    assert invfactory.classes_dir == (tmp_path / "inventory" / "classes")
    assert invfactory.targets_dir == (tmp_path / "inventory" / "targets")

    assert invfactory.classes_dir.exists()
    assert invfactory.classes_dir.is_dir()
    assert invfactory.targets_dir.exists()
    assert invfactory.targets_dir.is_dir()
    assert (invfactory.classes_dir / "global").exists()
    assert (invfactory.classes_dir / "global").is_symlink()


@pytest.mark.parametrize("distribution", ["a", "b", "c", "d"])
def test_inventoryfactory_reclass_distribution(tmp_path: Path, distribution: str):
    global_dir = setup_global_repo_dir(
        tmp_path, GLOBAL_PARAMS, DIST_PARAMS, CLOUD_REGION_PARAMS
    )
    invfacts = create_inventory_facts(
        tmp_path, global_dir, None, distribution, None, None
    )
    invfactory = parameters.InventoryFactory.from_repo_dirs(
        tmp_path, global_dir, None, invfacts
    )

    inv = invfactory.reclass(invfacts)
    components = inv.parameters("components")

    assert set(components.keys()) == set(GLOBAL_PARAMS["components"].keys())
    verify_components(components, distribution, None, None)


@pytest.mark.parametrize("cloud", ["x", "y", "z"])
def test_inventoryfactory_reclass_cloud(tmp_path: Path, cloud: str):
    global_dir = setup_global_repo_dir(
        tmp_path, GLOBAL_PARAMS, DIST_PARAMS, CLOUD_REGION_PARAMS
    )
    invfacts = create_inventory_facts(tmp_path, global_dir, None, None, cloud, None)
    invfactory = parameters.InventoryFactory.from_repo_dirs(
        tmp_path, global_dir, None, invfacts
    )

    inv = invfactory.reclass(invfacts)
    components = inv.parameters("components")

    assert set(components.keys()) == set(GLOBAL_PARAMS["components"].keys())
    verify_components(components, None, cloud, None)


@pytest.mark.parametrize("cloud,region", CLOUD_REGION_TESTCASES)
def test_inventoryfactory_reclass_cloud_region(tmp_path: Path, cloud: str, region: str):
    global_dir = setup_global_repo_dir(
        tmp_path, GLOBAL_PARAMS, DIST_PARAMS, CLOUD_REGION_PARAMS
    )
    invfacts = create_inventory_facts(tmp_path, global_dir, None, None, cloud, region)
    invfactory = parameters.InventoryFactory.from_repo_dirs(
        tmp_path, global_dir, None, invfacts
    )

    inv = invfactory.reclass(invfacts)
    components = inv.parameters("components")

    assert set(components.keys()) == set(GLOBAL_PARAMS["components"].keys())
    verify_components(components, None, cloud, region)


@pytest.mark.parametrize("cluster_id", CLUSTER_PARAMS.keys())
def test_inventoryfactory_reclass_tenant(tmp_path: Path, cluster_id: str):
    global_dir = setup_global_repo_dir(
        tmp_path, GLOBAL_PARAMS, DIST_PARAMS, CLOUD_REGION_PARAMS
    )
    tenant_dir = setup_tenant_repo_dir(tmp_path, CLUSTER_PARAMS)

    invfacts = create_inventory_facts(
        tmp_path, global_dir, tenant_dir, "a", "y", "m", cluster_id, "t-foo"
    )
    invfactory = parameters.InventoryFactory.from_repo_dirs(
        tmp_path, global_dir, tenant_dir, invfacts
    )
    inv = invfactory.reclass(invfacts)
    components = inv.parameters("components")

    assert set(components.keys()) == set(GLOBAL_PARAMS["components"].keys())
    verify_components(components, "a", "y", "m", cluster_id)
