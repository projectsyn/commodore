from __future__ import annotations

from pathlib import Path
from shutil import rmtree
from typing import Optional

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
    _automerge_patch: bool
    automerge_patch_v0: bool
    autorelease: bool
    _matrix_tests: bool
    _automerge_patch_blocklist: set[str]
    _automerge_patch_v0_allowlist: set[str]
    _automerge_minor_allowlist: set[str]

    def __init__(
        self,
        config: Config,
        template_url: str,
        template_version: Optional[str],
        slug: str,
        name: Optional[str] = None,
        output_dir: str = "",
    ):
        super().__init__(
            config,
            template_url,
            template_version,
            slug,
            name=name,
            output_dir=output_dir,
        )
        self._automerge_patch_blocklist = set()
        self._automerge_patch_v0_allowlist = set()
        self._automerge_minor_allowlist = set()

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
        self.automerge_patch = cookiecutter_args.get("automerge_patch", "y") == "y"
        self.automerge_patch_v0 = (
            cookiecutter_args.get("automerge_patch_v0", "n") == "y"
        )
        self.autorelease = cookiecutter_args.get("auto_release", "y") == "y"

        self._initialize_automerge_pattern_lists_from_cookiecutter_args(
            cookiecutter_args
        )

        return update_cruft_json

    def _initialize_automerge_pattern_lists_from_cookiecutter_args(
        self, cookiecutter_args: dict[str, str]
    ):
        args_patch_blocklist = cookiecutter_args.get(
            "automerge_patch_regexp_blocklist", ""
        )
        if args_patch_blocklist:
            self._automerge_patch_blocklist = set(args_patch_blocklist.split(";"))
        else:
            self._automerge_patch_blocklist = set()
        args_patch_v0_allowlist = cookiecutter_args.get(
            "automerge_patch_v0_regexp_allowlist", ""
        )
        if args_patch_v0_allowlist:
            self._automerge_patch_v0_allowlist = set(args_patch_v0_allowlist.split(";"))
        else:
            self._automerge_patch_v0_allowlist = set()
        args_minor_allowlist = cookiecutter_args.get(
            "automerge_minor_regexp_allowlist", ""
        )
        if args_minor_allowlist:
            self._automerge_minor_allowlist = set(args_minor_allowlist.split(";"))
        else:
            self._automerge_minor_allowlist = set()

    @property
    def cookiecutter_args(self) -> dict[str, str]:
        args = super().cookiecutter_args
        args["add_lib"] = "y" if self.library else "n"
        args["add_pp"] = "y" if self.post_process else "n"
        args["add_matrix"] = "y" if self.matrix_tests else "n"
        args["automerge_patch"] = "y" if self.automerge_patch else "n"
        args["automerge_patch_v0"] = "y" if self.automerge_patch_v0 else "n"
        args["auto_release"] = "y" if self.autorelease else "n"
        args["automerge_patch_regexp_blocklist"] = ";".join(
            sorted(self._automerge_patch_blocklist)
        )
        args["automerge_patch_v0_regexp_allowlist"] = ";".join(
            sorted(self._automerge_patch_v0_allowlist)
        )
        args["automerge_minor_regexp_allowlist"] = ";".join(
            sorted(self._automerge_minor_allowlist)
        )
        return args

    @property
    def automerge_patch(self) -> bool:
        if self.automerge_patch_v0:
            click.echo(
                " > Forcing automerging of patch dependencies to be enabled "
                + "when automerging of v0.x patch dependencies is requested"
            )
            return True
        return self._automerge_patch

    @automerge_patch.setter
    def automerge_patch(self, automerge_patch: bool) -> None:
        self._automerge_patch = automerge_patch

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

    def add_automerge_patch_block_pattern(self, pattern: str):
        """Add pattern to the patch automerge blocklist.

        `pattern` is expected to be a valid regex pattern.

        See `add_automerge_patch_block_depname()` for a variant of this method which
        will generate an anchored regex pattern for a particular dependency name.
        """
        self._automerge_patch_blocklist.add(pattern)

    def remove_automerge_patch_block_pattern(self, pattern: str):
        """Remove the given pattern from the patch blocklist."""
        try:
            self._automerge_patch_blocklist.remove(pattern)
        except KeyError:
            if self.config.verbose:
                click.echo(
                    f" > Pattern '{pattern}' isn't present in the automerge "
                    + "patch blocklist"
                )

    def add_automerge_patch_block_depname(self, name: str):
        """Add dependency to the patch automerge blocklist.

        This method generates an anchored regex pattern for the provided name and adds
        that pattern to the block list. See `add_automerge_patch_block_pattern()` for a
        variant which allows providing regex patterns directly.
        """
        self._automerge_patch_blocklist.add(f"^{name}$")

    def remove_automerge_patch_block_depname(self, name: str):
        """Remove the given dependency name from the patch blocklist.

        The function converts the dependency name into an anchored pattern to match the
        pattern that's added `add_automerge_patch_block_depname()` for the same value of
        `name`.
        """
        try:
            self._automerge_patch_blocklist.remove(f"^{name}$")
        except KeyError:
            if self.config.verbose:
                click.echo(
                    f" > Dependency name '{name}' isn't present in the automerge "
                    + "patch blocklist"
                )

    def add_automerge_patch_v0_allow_pattern(self, pattern: str):
        """Add pattern to the patch v0 automerge allowlist.

        `pattern` is expected to be a valid regex pattern.

        See `add_automerge_patch_v0_allow_depname()` for a variant of this method which
        will generate an anchored regex pattern for a particular dependency name.
        """
        self._automerge_patch_v0_allowlist.add(pattern)

    def remove_automerge_patch_v0_allow_pattern(self, pattern: str):
        """Remove the given pattern from the patch v0 allowlist."""
        try:
            self._automerge_patch_v0_allowlist.remove(pattern)
        except KeyError:
            if self.config.verbose:
                click.echo(
                    f" > Pattern '{pattern}' isn't present in the automerge "
                    + "patch v0 allowlist"
                )

    def add_automerge_patch_v0_allow_depname(self, name: str):
        """Add dependency to the patch v0 automerge allowlist.

        This method generates an anchored regex pattern for the provided name and adds
        that pattern to the allow list. See `add_automerge_patch_v0_allow_pattern()` for
        a variant which allows providing regex patterns directly.
        """
        self._automerge_patch_v0_allowlist.add(f"^{name}$")

    def remove_automerge_patch_v0_allow_depname(self, name: str):
        """Remove the given dependency name from the patch v0 allowlist.

        The function converts the dependency name into an anchored pattern to match the
        pattern that's added `add_automerge_patch_v0_allow_depname()` for the same value
        of `name`.
        """
        try:
            self._automerge_patch_v0_allowlist.remove(f"^{name}$")
        except KeyError:
            if self.config.verbose:
                click.echo(
                    f" > Dependency name '{name}' isn't present in the automerge "
                    + "patch v0 allowlist"
                )

    def add_automerge_minor_allow_pattern(self, pattern: str):
        """Add pattern to the minor automerge allowlist.

        `pattern` is expected to be a valid regex pattern.

        See `add_automerge_minor_allow_depname()` for a variant of this method which
        will generate an anchored regex pattern for a particular dependency name.
        """
        self._automerge_minor_allowlist.add(pattern)

    def remove_automerge_minor_allow_pattern(self, pattern: str):
        """Remove the given pattern from the minor allowlist."""
        try:
            self._automerge_minor_allowlist.remove(pattern)
        except KeyError:
            if self.config.verbose:
                click.echo(
                    f" > Pattern '{pattern}' isn't present in the automerge "
                    + "minor allowlist"
                )

    def add_automerge_minor_allow_depname(self, name: str):
        """Add dependency to the minor automerge allowlist.

        This method generates an anchored regex pattern for the provided name and adds
        that pattern to the allow list. See `add_automerge_minor_allow_pattern()` for a
        variant which allows providing regex patterns directly.
        """
        self._automerge_minor_allowlist.add(f"^{name}$")

    def remove_automerge_minor_allow_depname(self, name: str):
        """Remove the given dependency name from the minor allowlist.

        The function converts the dependency name into an anchored pattern to match the
        pattern that's added `add_automerge_minor_allow_depname()` for the same value of
        `name`.
        """
        try:
            self._automerge_minor_allowlist.remove(f"^{name}$")
        except KeyError:
            if self.config.verbose:
                click.echo(
                    f" > Dependency name '{name}' isn't present in the automerge "
                    + "minor allowlist"
                )

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
