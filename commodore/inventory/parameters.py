import os
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from kapitan.reclass import reclass
from kapitan.reclass.reclass import settings as reclass_settings
from kapitan.reclass.reclass import core as reclass_core
from kapitan.reclass.reclass import errors as reclass_errors

from commodore.cluster import Cluster, render_params
from commodore.component import component_parameters_key
from commodore.helpers import yaml_dump, yaml_load
from commodore.inventory import Inventory

FAKE_TENANT_ID = "t-foo"
FAKE_CLUSTER_ID = "c-bar"


class ClassNotFound(reclass_errors.ClassNotFound):
    """
    Create a wrapper around kapitan.reclass's ClassNotFound exception.

    This allows us to have clean exception handling outside of this file, because we
    unfortunately can't catch ClassNotFound directly in our code if we import
    and use Kapitan reclass's ClassNotFound with any import which doesn't map the class
    to `reclass.errors.ClassNotFound`. This is the case because Python's implementation
    doesn't try to figure out if two imports are the same if they have different import
    paths, cf. https://docs.python.org/3/reference/import.html.

    The only import that should work (in my understanding) would be
    `from kapitan.reclass import reclass` but with that import we get the error
    "AttributeError: module 'kapitan.reclass.reclass' has no attribute 'errors'"
    """

    @classmethod
    def from_reclass(cls, e: reclass_errors.ClassNotFound):
        """Wrap a reclass.errors.ClassNotFound instance in our wrapper."""
        return ClassNotFound(e.storage, e.name, e.path)


class InventoryFacts:
    def __init__(
        self,
        global_config: str,
        tenant_config: Optional[str],
        extra_class_files: Iterable[Path],
        allow_missing_classes: bool,
    ):
        self._global_config = global_config
        self._tenant_config = tenant_config
        self._extra_class_files = extra_class_files
        self._allow_missing_classes = allow_missing_classes

    @property
    def global_config(self) -> str:
        return self._global_config

    @property
    def tenant_config(self) -> Optional[str]:
        return self._tenant_config

    @property
    def extra_classes(self) -> List[str]:
        return [cf.stem for cf in self._extra_class_files]

    @property
    def extra_class_files(self) -> Iterable[Path]:
        return self._extra_class_files

    @property
    def allow_missing_classes(self) -> bool:
        return self._allow_missing_classes

    @property
    def tenant_id(self) -> str:
        tenant_id = None
        for f in self.extra_class_files:
            fc = yaml_load(f)
            tenant_id = (
                fc.get("parameters", {}).get("cluster", {}).get("tenant", tenant_id)
            )

        if not tenant_id:
            tenant_id = FAKE_TENANT_ID

        return tenant_id

    @property
    def cluster_id(self) -> str:
        cluster_id = None
        for f in self.extra_class_files:
            fc = yaml_load(f)
            cluster_id = (
                fc.get("parameters", {}).get("cluster", {}).get("name", cluster_id)
            )

        if not cluster_id:
            cluster_id = FAKE_CLUSTER_ID

        return cluster_id


class InventoryParameters:
    def __init__(self, inv):
        self._inventory = inv

    @property
    def distribution(self):
        return self._inventory["parameters"]["facts"]["distribution"]

    @property
    def cloud(self):
        return self._inventory["parameters"]["facts"]["cloud"]

    @property
    def region(self):
        return self._inventory["parameters"]["facts"]["region"]

    def parameters(self, param: Optional[str] = None):
        params = self._inventory["parameters"]
        if param is not None:
            params = params.get(component_parameters_key(param), {})

        return params

    @property
    def applications(self):
        return self._inventory["applications"]


class DefaultsFact(Enum):
    DISTRIBUTION = "distribution"
    CLOUD = "cloud"
    REGION = "region"


class InventoryFactory:
    def __init__(self, work_dir: Path, global_dir: Path, tenant_dir: Optional[Path]):
        self._global_dir = global_dir
        self._tenant_dir = tenant_dir
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

    @property
    def tenant_dir(self) -> Optional[Path]:
        return self._tenant_dir

    def _reclass_config(self, allow_missing_classes: bool) -> Dict:
        return {
            "storage_type": "yaml_fs",
            "inventory_base_uri": str(self.directory.absolute()),
            "nodes_uri": str(self.targets_dir.absolute()),
            "classes_uri": str(self.classes_dir.absolute()),
            "compose_node_name": False,
            "allow_none_override": True,
            "ignore_class_notfound": allow_missing_classes,
        }

    def _render_inventory(
        self, target: Optional[str] = None, allow_missing_classes: bool = True
    ) -> Dict[str, Any]:
        rc = self._reclass_config(allow_missing_classes)
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

        try:
            if target:
                return _reclass.nodeinfo(target)

            return _reclass.inventory()
        except Exception as e:
            if type(e).__name__ == "ClassNotFound":
                # Wrap Kapitan reclass's ClassNotFound with ours so we can cleanly
                # catch it. See docsstring for our ClassNotFound for a more detailed
                # explanation why this is necessary.
                raise ClassNotFound.from_reclass(e)
            raise

    def reclass(self, invfacts: InventoryFacts) -> InventoryParameters:
        cluster_response: Dict[str, Any] = {
            "id": invfacts.cluster_id,
            "tenant": invfacts.tenant_id,
            "displayName": "Foo Inc. Bar cluster",
            "facts": {
                "distribution": "x-fake-distribution",
                "cloud": "x-fake-cloud",
                "region": "x-fake-region",
                "lieutenant-instance": "lieutenant-prod",
            },
            "gitRepo": {
                "url": "not-a-real-repo",
            },
        }
        cluster = Cluster(
            cluster_response=cluster_response,
            tenant_response={
                "id": invfacts.tenant_id,
                "displayName": "Foo Inc.",
                "gitRepo": {
                    "url": "not-a-real-repo",
                },
            },
        )
        params = render_params(self._inventory, cluster)

        # Don't support legacy component_versions key
        # TODO: remove this when implementing issue #375
        del params["parameters"]["components"]
        del params["parameters"]["component_versions"]

        yaml_dump(params, self.classes_dir / "base.yml")

        # Create the following fake hierarchy for the render target:
        # classes:
        # - base
        # - user-supplied-file-1
        # - user-supplied-file-2
        # - ...
        # - global.commodore
        classes = ["base"] + invfacts.extra_classes + ["global.commodore"]
        yaml_dump(
            {
                "classes": classes,
                "parameters": {
                    "_instance": "global",
                },
            },
            self.targets_dir / "global.yml",
        )

        if not invfacts.tenant_config:
            # Create fake cluster class, this allows rendering the inventory with
            # allow-missing-classes=False to work when no tenant is specified.
            yaml_dump(
                {},
                self.classes_dir / FAKE_TENANT_ID / f"{FAKE_CLUSTER_ID}.yml",
            )

        return InventoryParameters(
            self._render_inventory(
                "global", allow_missing_classes=invfacts.allow_missing_classes
            )
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
    def from_repo_dirs(
        cls,
        work_dir: Path,
        global_dir: Path,
        tenant_dir: Optional[Path],
        invfacts: InventoryFacts,
    ):
        classes_dir = work_dir / "inventory" / "classes"
        os.makedirs(work_dir / "inventory" / "targets", exist_ok=True)
        os.makedirs(classes_dir, exist_ok=True)
        if not tenant_dir:
            os.makedirs(
                work_dir / "inventory" / "classes" / FAKE_TENANT_ID, exist_ok=True
            )
        os.symlink(global_dir.absolute(), classes_dir / "global")
        if tenant_dir:
            os.symlink(tenant_dir.absolute(), classes_dir / invfacts.tenant_id)
        for cf in invfacts.extra_class_files:
            os.symlink(cf.absolute(), classes_dir / cf.name)
        return InventoryFactory(
            work_dir=work_dir,
            global_dir=classes_dir / "global",
            tenant_dir=classes_dir / invfacts.tenant_id,
        )
