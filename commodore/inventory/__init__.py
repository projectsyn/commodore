from os import makedirs
from pathlib import Path as P
from typing import Union

from commodore.component import Component


class Inventory:
    _work_dir: P

    def __init__(self, work_dir: P = None):
        if work_dir:
            self._work_dir = work_dir
        else:
            self._work_dir = P(".")

    @property
    def work_dir(self) -> P:
        return self._work_dir

    @work_dir.setter
    def work_dir(self, d: P):
        self._work_dir = d

    @property
    def inventory_dir(self) -> P:
        return self._work_dir / "inventory"

    @property
    def dependencies_dir(self) -> P:
        return self._work_dir / "dependencies"

    @property
    def classes_dir(self) -> P:
        return self.inventory_dir / "classes"

    @property
    def components_dir(self) -> P:
        return self.classes_dir / "components"

    @property
    def defaults_dir(self) -> P:
        return self.classes_dir / "defaults"

    @property
    def targets_dir(self) -> P:
        return self.inventory_dir / "targets"

    @property
    def lib_dir(self) -> P:
        return self.dependencies_dir / "lib"

    @property
    def libs_dir(self) -> P:
        return self.dependencies_dir / "libs"

    @property
    def global_config_dir(self) -> P:
        return self.classes_dir / "global"

    @property
    def bootstrap_target(self) -> str:
        return "cluster"

    @property
    def params_dir(self) -> P:
        return self.classes_dir / "params"

    @property
    def params_file(self) -> P:
        return self.params_dir / f"{self.bootstrap_target}.yml"

    @property
    def output_dir(self) -> P:
        return self._work_dir / "compiled"

    def tenant_config_dir(self, tenant: str) -> P:
        return self.classes_dir / tenant

    # pylint: disable=unsubscriptable-object
    def component_file(self, component: Union[Component, str]) -> P:
        return self.components_dir / f"{_component_name(component)}.yml"

    # pylint: disable=unsubscriptable-object
    def defaults_file(self, component: Union[Component, str]) -> P:
        return self.defaults_dir / f"{_component_name(component)}.yml"

    # pylint: disable=unsubscriptable-object
    def target_file(self, target: Union[Component, str]) -> P:
        return self.targets_dir / f"{_component_name(target)}.yml"

    def ensure_dirs(self):
        makedirs(self.components_dir, exist_ok=True)
        makedirs(self.defaults_dir, exist_ok=True)
        makedirs(self.params_dir, exist_ok=True)
        makedirs(self.lib_dir, exist_ok=True)
        makedirs(self.libs_dir, exist_ok=True)
        makedirs(self.targets_dir, exist_ok=True)


# pylint: disable=unsubscriptable-object
def _component_name(component: Union[Component, str]) -> str:
    if isinstance(component, Component):
        return component.name

    return component
