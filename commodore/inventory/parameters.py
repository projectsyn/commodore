import os
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from kapitan.reclass import reclass
from kapitan.reclass.reclass import settings as reclass_settings
from kapitan.reclass.reclass import core as reclass_core

from commodore.cluster import Cluster, render_params
from commodore.component import component_parameters_key
from commodore.helpers import yaml_dump
from commodore.inventory import Inventory


class InventoryFacts:
    # pylint: disable=too-many-arguments
    def __init__(self, global_config, tenant_config, distribution, cloud, region):
        self._global_config = global_config
        self._tenant_config = tenant_config
        self._distribution = distribution
        self._cloud = cloud
        self._region = region

    @property
    def global_config(self):
        return self._global_config

    @property
    def tenant_config(self):
        return self._tenant_config

    @property
    def distribution(self):
        return self._distribution

    @property
    def cloud(self):
        return self._cloud

    @property
    def region(self):
        return self._region


class InventoryParameters:
    def __init__(self, inv, node, invfacts: InventoryFacts):
        self._inventory = inv
        self._node = node
        self._distribution = invfacts.distribution
        self._cloud = invfacts.cloud
        self._region = invfacts.region

    @property
    def distribution(self):
        return self._distribution

    @property
    def cloud(self):
        return self._cloud

    @property
    def region(self):
        return self._region

    def parameters(self, param: Optional[str] = None):
        params = self._inventory["nodes"][self._node]["parameters"]
        if param is not None:
            params = params.get(component_parameters_key(param), {})

        return params

    @property
    def applications(self):
        return self._inventory["nodes"][self._node]["applications"]


class DefaultsFact(Enum):
    DISTRIBUTION = "distribution"
    CLOUD = "cloud"
    REGION = "region"


class InventoryFactory:
    def __init__(self, work_dir: Path, global_dir: Path):
        self._global_dir = global_dir
        self._inventory = Inventory(work_dir=work_dir)
        self._distributions = self._find_values(DefaultsFact.DISTRIBUTION)
        self._clouds = self._find_values(DefaultsFact.CLOUD)
        self._cloud_regions: Dict[str, Iterable[str]] = {}
        for cloud in self._clouds:
            r = self._find_values(DefaultsFact.REGION, cloud=cloud)
            self._cloud_regions[cloud] = [it for it in r if it != "params"]

    @property
    def directory(self) -> Path:
        return self._inventory.inventory_dir

    @property
    def classes_dir(self) -> Path:
        return self._inventory.classes_dir

    @property
    def targets_dir(self) -> Path:
        return self._inventory.targets_dir

    @property
    def global_dir(self) -> Path:
        return self._global_dir

    def _reclass_config(self) -> Dict:
        return {
            "storage_type": "yaml_fs",
            "inventory_base_uri": str(self.directory.absolute()),
            "nodes_uri": str(self.targets_dir.absolute()),
            "classes_uri": str(self.classes_dir.absolute()),
            "compose_node_name": False,
            "allow_none_override": True,
            "ignore_class_notfound": True,
        }

    def reclass(self, invfacts: InventoryFacts) -> InventoryParameters:
        distribution = invfacts.distribution
        cloud = invfacts.cloud
        region = invfacts.region
        if distribution is None:
            distribution = "x-fake-distribution"
        if cloud is None:
            cloud = "x-fake-cloud"
        if region is None:
            region = "x-fake-region"

        c: Dict[str, Any] = {
            "id": "c-bar",
            "tenant": "t-foo",
            "displayName": "Foo Inc. Bar cluster",
            "facts": {
                "distribution": distribution,
                "cloud": cloud,
                "lieutenant-instance": "lieutenant-prod",
                f"{distribution}_version": "1.20",
            },
            "gitRepo": {
                "url": "not-a-real-repo",
            },
        }
        if region:
            c["facts"]["region"] = region

        cluster = Cluster(
            cluster_response=c,
            tenant_response={
                "id": "t-foo",
                "displayName": "Foo Inc.",
                "gitRepo": {
                    "url": "not-a-real-repo",
                },
            },
        )
        params = render_params(self._inventory, cluster)
        # don't support legacy component_versions key
        del params["parameters"]["components"]
        del params["parameters"]["component_versions"]
        params["parameters"]["openshift"] = {
            "infraID": "infra-id",
            "clusterID": "clutster-id",
            "registryBucket": "x-fake-registry-bucket",
        }
        params["parameters"]["cloud"]["availabilityZones"] = []
        params["parameters"]["cloud"]["projectName"] = "x-fake-project"

        yaml_dump(params, self.classes_dir / "target.yml")
        yaml_dump(
            {"classes": ["target", "global.commodore"]},
            self.targets_dir / "global.yml",
        )
        rc = self._reclass_config()
        storage = reclass.get_storage(
            rc["storage_type"],
            rc["nodes_uri"],
            rc["classes_uri"],
            rc["compose_node_name"],
        )
        class_mappings = rc.get("class_mappings")
        _reclass = reclass_core.Core(
            storage, class_mappings, reclass_settings.Settings(rc)
        )
        return InventoryParameters(
            _reclass.inventory(),
            "global",
            InventoryFacts(None, None, distribution, cloud, region),
        )

    def _find_values(self, fact: DefaultsFact, cloud: str = None) -> Iterable[str]:
        values = []
        value_path = self.global_dir / fact.value
        if fact == DefaultsFact.REGION:
            if not cloud:
                raise ValueError(f"cloud must not be None if fact is {fact}")
            value_path = self.global_dir / "cloud" / cloud
        if value_path.is_dir():
            for f in value_path.iterdir():
                if f.is_file() and f.suffix in (".yml", ".yaml"):
                    values.append(f.stem)
        return values

    @property
    def distributions(self) -> Iterable[str]:
        return self._distributions

    @property
    def clouds(self) -> Iterable[str]:
        return self._clouds

    @property
    def cloud_regions(self) -> Dict[str, Iterable[str]]:
        return self._cloud_regions

    @classmethod
    def _make_directories(cls, work_dir: Path):
        os.makedirs(work_dir / "inventory" / "targets", exist_ok=True)
        os.makedirs(work_dir / "inventory" / "classes", exist_ok=True)

    @classmethod
    def from_repo_dir(cls, work_dir: Path, global_dir: Path):
        cls._make_directories(work_dir)
        classes_dir = work_dir / "inventory" / "classes"
        os.symlink(global_dir.absolute(), classes_dir / "global")
        return InventoryFactory(work_dir=work_dir, global_dir=classes_dir / "global")
