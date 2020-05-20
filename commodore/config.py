from collections import namedtuple
from pathlib import Path as P

Component = namedtuple('Component', ['name', 'repo', 'version'])


class Config:
    # pylint: disable=too-many-arguments
    def __init__(self, api_url, api_token, global_git, verbose):
        self.api_url = api_url
        self.api_token = None
        if api_token is not None:
            try:
                p = P(api_token)
                if p.is_file():
                    with open(p) as apitoken:
                        api_token = apitoken.read()
            except OSError:
                # Assume token is not configured as file
                pass
            self.api_token = api_token.strip()
        self.global_git_base = global_git
        self._components = {}
        self._config_repos = {}
        self._verbose = verbose

    @property
    def verbose(self):
        return self._verbose

    @property
    def debug(self):
        return self._verbose > 0

    @property
    def trace(self):
        return self._verbose >= 3

    def update_verbosity(self, verbose):
        self._verbose += verbose

    def get_components(self):
        return self._components

    def register_component(self, component, repo):
        c = Component(
            name=component,
            repo=repo,
            version='master',
        )
        self._components[component] = c

    def set_component_version(self, component, version):
        c = self._components[component]
        c = c._replace(version=version)
        self._components[component] = c

    def get_component_repo(self, component):
        return self._components[component].repo

    def get_configs(self):
        return self._config_repos

    def register_config(self, level, repo):
        self._config_repos[level] = repo
