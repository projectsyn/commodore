from collections import namedtuple
from enum import Enum

Component = namedtuple('Component', ['name', 'repo', 'version'])

class Config(object):
    def __init__(self, api_url, global_git, customer_git):
        self.api_url = api_url
        self.global_git_base = global_git
        self.customer_git_base = customer_git
        self._components = {}

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
