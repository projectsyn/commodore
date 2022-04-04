from pathlib import Path as P
from typing import Dict, Iterable, Optional

import _jsonnet
import click
import yaml

from commodore.gitrepo import GitRepo


class Component:
    _name: str
    _repo: GitRepo
    _version: Optional[str] = None
    _dir: P

    # pylint: disable=too-many-arguments
    def __init__(
        self,
        name: str,
        work_dir: P = None,
        repo_url: str = None,
        version: str = None,
        force_init: bool = False,
        directory: P = None,
    ):
        self._name = name
        if directory:
            self._dir = directory
        elif work_dir:
            self._dir = component_dir(work_dir, self.name)
        else:
            raise click.ClickException(
                "Either `work_dir` or `directory` must be provided."
            )
        self._repo = GitRepo(repo_url, self._dir, force_init=force_init)
        self.version = version

    @property
    def name(self) -> str:
        return self._name

    @property
    def repo(self) -> GitRepo:
        return self._repo

    @property
    def repo_url(self) -> str:
        return self._repo.remote

    @repo_url.setter
    def repo_url(self, repo_url: str):
        self._repo.remote = repo_url

    @property
    def version(self) -> Optional[str]:
        return self._version

    @version.setter
    def version(self, version: str):
        self._version = version

    @property
    def target_directory(self) -> P:
        return self._dir

    @property
    def class_file(self) -> P:
        return self.target_directory / "class" / f"{self.name}.yml"

    @property
    def defaults_file(self) -> P:
        return self.target_directory / "class" / "defaults.yml"

    @property
    def default_values(self) -> Dict:
        with open(self.defaults_file, "r", encoding="utf-8") as f:
            defyaml = list(yaml.safe_load_all(f))
        return defyaml[0]["parameters"][self.parameters_key]

    @property
    def lib_files(self) -> Iterable[P]:
        lib_dir = self.target_directory / "lib"
        if lib_dir.exists():
            return lib_dir.iterdir()

        return []

    def get_library(self, libname: str) -> P:
        lib_dir = self.target_directory / "lib"
        if not lib_dir.exists():
            return None

        for f in self.lib_files:
            if f.absolute() == P(lib_dir / libname).absolute():
                return f.absolute()

        return None

    @property
    def filters_file(self) -> P:
        return self.target_directory / "postprocess" / "filters.yml"

    @property
    def parameters_key(self):
        return component_parameters_key(self.name)

    def checkout(self):
        self._repo.checkout(self.version)

    def render_jsonnetfile_json(self, component_params):
        """
        Render jsonnetfile.json from jsonnetfile.jsonnet
        """
        jsonnetfile_jsonnet = self._dir / "jsonnetfile.jsonnet"
        jsonnetfile_json = self._dir / "jsonnetfile.json"
        if jsonnetfile_jsonnet.is_file():
            if jsonnetfile_json.name in self._repo.repo.tree():
                click.secho(
                    f" > [WARN] Component {self.name} repo contains both jsonnetfile.json and jsonnetfile.jsonnet, "
                    + "continuing with jsonnetfile.jsonnet",
                    fg="yellow",
                )
            # pylint: disable=c-extension-no-member
            output = _jsonnet.evaluate_file(
                str(jsonnetfile_jsonnet),
                ext_vars=component_params.get("jsonnetfile_parameters", {}),
            )
            with open(self._dir / "jsonnetfile.json", "w", encoding="utf-8") as fp:
                fp.write(output)
                fp.write("\n")


def component_dir(work_dir: P, name: str) -> P:
    return work_dir / "dependencies" / name


def component_parameters_key(name: str) -> str:
    return name.replace("-", "_")
