from __future__ import annotations

from pathlib import Path
from shutil import rmtree

import click
import git
import yaml

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

    @property
    def _has_lib(self) -> bool:
        """Determine whether component has a component library by checking the presence
        of the `lib` folder."""
        return (self.target_dir / "lib").is_dir()

    @property
    def _has_pp(self) -> bool:
        """Determine whether component has postprocessing filters by looking at the
        component class contents."""
        with open(
            self.target_dir / "class" / f"{self.slug}.yml", "r", encoding="utf-8"
        ) as cls:
            class_data = yaml.safe_load(cls)
            return "postprocess" in class_data["parameters"].get("commodore", {})

    def _initialize_from_cookiecutter_args(self, cookiecutter_args: dict[str, str]):
        update_cruft_json = super()._initialize_from_cookiecutter_args(
            cookiecutter_args
        )

        if "add_lib" not in cookiecutter_args:
            # If `add_lib` is not present in the cookiecutter args, determine if the
            # component has a component library and set the arg in `cookiecutter_args`
            # accordingly.
            cookiecutter_args["add_lib"] = "y" if self._has_lib else "n"
            update_cruft_json = True

        if "add_pp" not in cookiecutter_args:
            # If `add_pp` is not present in the cookiecutter args, determine if the
            # component has postprocessing filters and set the arg in
            # `cookiecutter_args` accordingly.
            cookiecutter_args["add_pp"] = "y" if self._has_pp else "n"
            update_cruft_json = True

        if (self.target_dir / ".sync.yml").is_file():
            # Migrate copyright information from modulesync config, if it's present and
            # the information is missing in the cookiecutter args.
            with open(self.target_dir / ".sync.yml", "r", encoding="utf-8") as f:
                sync_yml = yaml.safe_load(f)
            license_data = sync_yml.get("LICENSE", {})
            if "copyright_holder" not in cookiecutter_args:
                cookiecutter_args["copyright_holder"] = license_data.get(
                    "holder", "VSHN AG <info@vshn.ch>"
                )
                update_cruft_json = True
            self.copyright_holder = cookiecutter_args["copyright_holder"]
            if "copyright_year" not in cookiecutter_args:
                cookiecutter_args["copyright_year"] = str(
                    license_data.get("year", 2021)
                )
                update_cruft_json = True
            self.copyright_year = cookiecutter_args["copyright_year"]

        self.library = cookiecutter_args["add_lib"] == "y"
        self.post_process = cookiecutter_args["add_pp"] == "y"
        self.matrix_tests = cookiecutter_args["add_matrix"] == "y"

        return update_cruft_json

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
