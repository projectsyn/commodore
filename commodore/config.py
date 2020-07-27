from typing import NamedTuple
from pathlib import Path as P

from git import Repo


class Component(NamedTuple):
    name: str
    repo: Repo
    repo_url: str
    version: str = 'master'

    @property
    def target_directory(self):
        return P('dependencies') / self.name


# pylint: disable=too-many-instance-attributes
class Config:
    # pylint: disable=too-many-arguments
    def __init__(self, api_url=None, api_token=None, global_git=None, verbose=False, username=None, usermail=None):
        self.api_url = api_url
        self.api_token = None
        self.api_token = api_token
        self.global_git_base = global_git
        self._components = {}
        self._config_repos = {}
        self._verbose = verbose

        self.username = username
        self.usermail = usermail

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
        return 'inventory/classes/global/commodore.yml'

    @property
    def default_component_base(self):
        return f"{self.global_git_base}/commodore-components"

    @property
    def api_token(self):
        return self._api_token

    @api_token.setter
    def api_token(self, api_token):
        if api_token is not None:
            p = P(api_token)
            if p.is_file():
                with open(p) as apitoken:
                    api_token = apitoken.read()
            self._api_token = api_token.strip()

    def update_verbosity(self, verbose):
        self._verbose += verbose

    def get_components(self):
        return self._components

    def register_component(self, component: Component):
        self._components[component.name] = component

    def set_component_version(self, component_name, version):
        c = self._components[component_name]
        c = c._replace(version=version)
        self._components[component_name] = c
        return c

    def set_repo_url(self, component_name, repo_url):
        c = self._components[component_name]
        c = c._replace(repo_url=repo_url)
        self._components[component_name] = c
        return c

    def get_component_repo(self, component_name):
        return self._components[component_name].repo

    def get_configs(self):
        return self._config_repos

    def register_config(self, level, repo):
        self._config_repos[level] = repo
