from __future__ import annotations

from pathlib import Path
from shutil import rmtree

import click
import git

from commodore.config import Config
from commodore.component import Component, component_dir
from commodore.dependency_templater import Templater
from commodore.multi_dependency import MultiDependency


class ComponentTemplater(Templater):
    library: bool
    post_process: bool
    _matrix_tests: bool

    @classmethod
    def from_existing(cls, config: Config, path: Path):
        return cls._base_from_existing(config, path, "component")

    def _initialize_from_cookiecutter_args(self, cookiecutter_args: dict[str, str]):
        super()._initialize_from_cookiecutter_args(cookiecutter_args)
        self.library = cookiecutter_args["add_lib"] == "y"
        self.post_process = cookiecutter_args["add_pp"] == "y"
        self.matrix_tests = cookiecutter_args["add_matrix"] == "y"

    @property
    def cookiecutter_args(self) -> dict[str, str]:
        args = super().cookiecutter_args
        args["add_lib"] = "y" if self.library else "n"
        args["add_pp"] = "y" if self.post_process else "n"
        args["add_matrix"] = "y" if self.matrix_tests else "n"
        return args

    @property
    def matrix_tests(self) -> bool:
        if len(self.test_cases) > 1:
            if not self._matrix_tests:
                click.echo(" > Forcing matrix tests when multiple test cases requested")
            return True
        return self._matrix_tests

    @matrix_tests.setter
    def matrix_tests(self, matrix_tests: bool) -> None:
        self._matrix_tests = matrix_tests

    @property
    def deptype(self) -> str:
        return "component"

    def dependency_dir(self) -> Path:
        return component_dir(self.config.work_dir, self.slug)

    def delete(self):
        cdir = component_dir(self.config.work_dir, self.slug)
        if cdir.exists():
            cr = git.Repo(cdir)
            cdep = MultiDependency(
                cr.remote().url, self.config.inventory.dependencies_dir
            )
            component = Component(
                self.slug, dependency=cdep, work_dir=self.config.work_dir
            )

            if not self.config.force:
                click.confirm(
                    "Are you sure you want to delete component "
                    f"{self.slug}? This action cannot be undone",
                    abort=True,
                )
            rmtree(component.target_directory)
            # We check for other checkouts here, because our MultiDependency doesn't
            # know if there's other dependencies which would be registered on it.
            if not cdep.has_checkouts():
                # Also delete bare copy of component repo, if there's no other
                # worktree checkouts for the same dependency repo.
                rmtree(cdep.repo_directory)
            else:
                click.echo(
                    f" > Not deleting bare copy of repository {cdep.url}. "
                    + "Other worktrees refer to the same reposiotry."
                )

            click.secho(f"Component {self.slug} successfully deleted 🎉", bold=True)
        else:
            raise click.BadParameter(
                "Cannot find component with slug " f"'{self.slug}'."
            )
