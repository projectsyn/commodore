from pathlib import Path as P
from typing import Dict

import click
from git import Repo

from commodore.component import Component, component_parameters_key
from .inventory import Inventory


# pylint: disable=too-many-instance-attributes,too-many-public-methods
class Config:
    _inventory: Inventory
    _components: Dict[str, Component]
    _config_repos: Dict[str, Repo]
    _component_aliases: Dict[str, str]

    # pylint: disable=too-many-arguments
    def __init__(
        self,
        work_dir: P,
        api_url=None,
        api_token=None,
        verbose=0,
        username=None,
        usermail=None,
    ):
        self._work_dir = work_dir.resolve()
        self.api_url = api_url
        self.api_token = None
        self.api_token = api_token
        self._components = {}
        self._config_repos = {}
        self._component_aliases = {}
        self._verbose = verbose
        self.username = username
        self.usermail = usermail
        self.local = None
        self.push = None
        self.interactive = None
        self.force = False
        self._inventory = Inventory(work_dir=self.work_dir)

    @property
    def verbose(self):
        return self._verbose

    @property
    def debug(self):
        return self._verbose > 0

    @property
    def trace(self):
        return self._verbose >= 3

    @property
    def config_file(self):
        return self._inventory.global_config_dir / "commodore.yml"

    @property
    def jsonnet_file(self) -> P:
        return self._work_dir / "jsonnetfile.json"

    @property
    def work_dir(self) -> P:
        return self._work_dir

    @work_dir.setter
    def work_dir(self, d: P):
        self._work_dir = d
        self.inventory.work_dir = d

    @property
    def vendor_dir(self) -> P:
        return self.work_dir / "vendor"

    @property
    def catalog_dir(self) -> P:
        return self.work_dir / "catalog"

    @property
    def refs_dir(self) -> P:
        return self.catalog_dir / "refs"

    @property
    def api_token(self):
        return self._api_token

    @api_token.setter
    def api_token(self, api_token):
        if api_token is not None:
            try:
                p = P(api_token)
                if p.is_file():
                    with open(p) as apitoken:
                        api_token = apitoken.read()
            except OSError as e:
                # File name too long, assume token is not configured as file
                if "File name too long" in e.strerror:
                    pass
                else:
                    raise
            self._api_token = api_token.strip()

    @property
    def inventory(self):
        return self._inventory

    def update_verbosity(self, verbose):
        self._verbose += verbose

    def get_components(self):
        return self._components

    def register_component(self, component: Component):
        self._components[component.name] = component

    def get_component_repo(self, component_name):
        return self._components[component_name].repo

    def get_configs(self):
        return self._config_repos

    def register_config(self, level, repo):
        self._config_repos[level] = repo

    def get_component_aliases(self):
        return self._component_aliases

    def register_component_aliases(self, aliases: Dict[str, str]):
        self._component_aliases = aliases

    def verify_component_aliases(self, cluster_parameters: Dict):
        for alias, cn in self._component_aliases.items():
            ckey = component_parameters_key(cn)
            caliasable = cluster_parameters[ckey].get("multi_instance", False)
            if alias != cn and not caliasable:
                raise click.ClickException(
                    f"Component {cn} with alias {alias} does not support instantiation."
                )
