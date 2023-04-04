from __future__ import annotations

import datetime
import difflib
import json
import re
import tempfile
import shutil
import textwrap

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

import click

from cruft import create as cruft_create, update as cruft_update

from commodore.config import Config
from commodore.gitrepo import GitRepo, MergeConflict, default_difffunc
from commodore.multi_dependency import MultiDependency

SLUG_REGEX = re.compile("^[a-z][a-z0-9-]+[a-z0-9]$")

REJ_IGNORE = re.compile(r"\.(orig|rej)$")


def _ignore_cruft_json_commit_id(
    before_text: str, after_text: str, fromfile: str = "", tofile: str = ""
):
    """Custom diff function which omits `.cruft.json` diffs which only differ in the
    template commit id."""
    before_lines = before_text.split("\n")
    after_lines = after_text.split("\n")
    diff_lines = difflib.unified_diff(
        before_lines, after_lines, lineterm="", fromfile=fromfile, tofile=tofile
    )
    omit = False
    if fromfile == ".cruft.json" and tofile == ".cruft.json":
        # Compute diff without context lines for `.cruft.json` (n=0) and drop the
        # unified diff header (first 3 lines).
        minimal_diff = list(
            difflib.unified_diff(
                before_lines,
                after_lines,
                lineterm="",
                fromfile=fromfile,
                tofile=tofile,
                n=0,
            )
        )[3:]
        # If the context-less diff has exactly 2 lines and both of them start with
        # '[-+] "commit":', we omit the diff
        if (
            len(minimal_diff) == 2
            and minimal_diff[0].startswith('-  "commit":')
            and minimal_diff[1].startswith('+  "commit":')
        ):
            omit = True
    # never suppress diffs in default difffunc
    return diff_lines, omit


class Templater(ABC):
    config: Config
    _slug: str
    _name: Optional[str]
    github_owner: str
    copyright_holder: str
    copyright_year: Optional[str] = None
    golden_tests: bool
    today: datetime.date
    output_dir: Optional[Path] = None
    _target_dir: Optional[Path] = None
    template_url: str
    template_version: Optional[str] = None
    _test_cases: list[str] = ["defaults"]

    def __init__(
        self,
        config: Config,
        template_url: str,
        template_version: Optional[str],
        slug: str,
        name: Optional[str] = None,
        output_dir: str = "",
    ):
        self.config = config
        self.template_url = template_url
        self.template_version = template_version
        self.slug = slug
        self._name = name
        self.today = datetime.date.today()
        if output_dir != "":
            odir = Path(output_dir)
            if not odir.is_dir():
                raise click.ClickException(f"Output directory {odir} doesn't exist")

            self.output_dir = odir

    @classmethod
    @abstractmethod
    def from_existing(cls, config: Config, path: Path):
        ...

    @classmethod
    def _base_from_existing(cls, config: Config, path: Path, deptype: str):
        if not path.is_dir():
            raise click.ClickException(f"Provided {deptype} path isn't a directory")
        if not (path / ".cruft.json").is_file():
            raise click.ClickException(
                f"Provided {deptype} path doesn't have `.cruft.json`, can't update."
            )
        with open(path / ".cruft.json", encoding="utf-8") as cfg:
            cruft_json = json.load(cfg)

        cookiecutter_args = cruft_json["context"]["cookiecutter"]
        t = cls(
            config,
            cruft_json["template"],
            cruft_json.get("checkout"),
            cookiecutter_args["slug"],
            name=cookiecutter_args["name"],
        )
        t._target_dir = path
        t.output_dir = path.absolute().parent

        # We pass the cookiecutter args dict to `_initialize_from_cookiecutter_args()`.
        # Because Python dicts are passed by reference, the function can simply add
        # missing args into the dict and return `True` to cause us to write back and
        # commit the updated `.cruft.json` data.
        update_cruft_json = t._initialize_from_cookiecutter_args(cookiecutter_args)

        if update_cruft_json:
            click.echo(" > Adding missing cookiecutter args to `.cruft.json`")
            with open(path / ".cruft.json", "w", encoding="utf-8") as f:
                json.dump(cruft_json, f, indent=2)
                f.write("\n")
            r = GitRepo(
                None,
                path,
                author_name=config.username,
                author_email=config.usermail,
            )
            r.stage_files([".cruft.json"])
            r.commit("Add missing cookiecutter args to `.cruft.json`")

        return t

    @property
    @abstractmethod
    def deptype(self) -> str:
        """Return dependency type of template as string.

        The base implementation of `_validate_slug()` will reject slugs which are
        prefixed with the value of this property.
        """

    @abstractmethod
    def dependency_dir(self) -> Path:
        """Location of dependency in the Commodore working directory.

        Used by `target_dir()` if neither `_target_dir` nor `_output_dir` is set."""

    @property
    def target_dir(self) -> Path:
        """Return Path indicating where to render the template to."""
        if self._target_dir:
            return self._target_dir

        if self.output_dir:
            return self.output_dir / self.slug

        return self.dependency_dir()

    @property
    def cookiecutter_args(self) -> dict[str, str]:
        """Cookiecutter template inputs.

        Passed to the rendering function as `extra_context`

        The method tries to load cookiecutter args from the dependency's `.cruft.json`
        but doesn't fail if it doesn't find a `.cruft.json`. This approach allows us to
        handle templates with unknown cookiecutter args.
        """
        local_args = {
            "add_golden": "y" if self.golden_tests else "n",
            "copyright_holder": self.copyright_holder,
            "copyright_year": (
                self.today.strftime("%Y")
                if not self.copyright_year
                else self.copyright_year
            ),
            "github_owner": self.github_owner,
            "name": self.name,
            "slug": self.slug,
            # The template expects the test cases in a single string separated by
            # spaces.
            "test_cases": " ".join(self.test_cases),
        }
        cruft_json = self.target_dir / ".cruft.json"
        if cruft_json.is_file():
            with open(cruft_json, "r", encoding="utf-8") as f:
                cruft_json_data = json.load(f)
                args = cruft_json_data["context"]["cookiecutter"]
            for k, v in local_args.items():
                args[k] = v
        else:
            args = local_args

        return args

    def _initialize_from_cookiecutter_args(self, cookiecutter_args: dict[str, str]):
        """This method sets the class properties corresponding to the cookiecutter
        template args from the provided cookiecutter_args dict.

        The method returns a boolean which indicates if the method extended the provided
        args dict with missing template args. If the method returns `True`, the caller
        should ensure that the updated args dict is written back to `.cruft.json`."""
        self.golden_tests = cookiecutter_args["add_golden"] == "y"
        self.github_owner = cookiecutter_args["github_owner"]
        # Allow copyright holder and copyright year to be missing in the cookiecutter
        # args. Fallback to VSHN AG <info@vshn.ch> and the current year here.
        self.copyright_holder = cookiecutter_args.get(
            "copyright_holder", "VSHN AG <info@vshn.ch>"
        )
        self.copyright_year = cookiecutter_args.get("copyright_year")
        if "test_cases" in cookiecutter_args:
            self.test_cases = cookiecutter_args["test_cases"].split(" ")
        else:
            self.test_cases = ["defaults"]

        return False

    def _validate_slug(self, value: str) -> str:
        if value.startswith(f"{self.deptype}-"):
            raise click.ClickException(
                f"The {self.deptype} slug may not start with '{self.deptype}-'"
            )
        if not SLUG_REGEX.match(value):
            raise click.ClickException(
                f"The {self.deptype} slug must match '{SLUG_REGEX.pattern}'"
            )
        return value

    @property
    def slug(self) -> str:
        return self._slug

    @slug.setter
    def slug(self, value: str):
        self._slug = self._validate_slug(value)

    @property
    def name(self) -> str:
        if not self._name:
            return self.slug
        return self._name

    @property
    def repo_url(self) -> str:
        return f"git@github.com:{self.github_owner}/{self.deptype}-{self.slug}.git"

    @property
    def test_cases(self) -> list[str]:
        """Return list of test cases.

        The getter deduplicates the stored list before returning it.

        Don't use `append()` on the returned list to add test cases to the package, as
        the getter returns a copy of the list stored in the object."""
        cases = []
        for t in self._test_cases:
            if t not in cases:
                cases.append(t)
        return cases

    @test_cases.setter
    def test_cases(self, test_cases: list[str]):
        self._test_cases = test_cases

    @property
    def template_commit(self) -> Optional[str]:
        cruft_json = self.target_dir / ".cruft.json"
        if not cruft_json.is_file():
            click.echo(
                f" > {self.deptype.capitalize()} doesn't have a `.cruft.json`, "
                + "can't determine template commit."
            )
            return None

        with open(cruft_json, "r", encoding="utf-8") as f:
            cruft_json_data = json.load(f)
            return cruft_json_data["commit"]

    def create(self) -> None:
        click.secho(f"Adding {self.deptype} {self.name}...", bold=True)

        if self.target_dir.exists():
            raise click.ClickException(
                f"Unable to add {self.deptype} {self.name}: "
                + f"{self.target_dir} already exists."
            )

        want_worktree = (
            self.config.inventory.dependencies_dir in self.target_dir.parents
        )
        if want_worktree:
            md = MultiDependency(self.repo_url, self.config.inventory.dependencies_dir)
            md.initialize_worktree(self.target_dir)

        with tempfile.TemporaryDirectory() as tmpdir:
            cruft_create(
                self.template_url,
                checkout=self.template_version,
                extra_context=self.cookiecutter_args,
                no_input=True,
                output_dir=Path(tmpdir),
            )
            shutil.copytree(
                Path(tmpdir) / self.slug, self.target_dir, dirs_exist_ok=True
            )

        self.commit("Initial commit", amend=want_worktree)
        click.secho(
            f"{self.deptype.capitalize()} {self.name} successfully added 🎉", bold=True
        )

    def update(
        self,
        print_completion_message: bool = True,
        commit: bool = True,
        ignore_template_commit: bool = False,
    ) -> bool:
        if len(self.test_cases) == 0:
            raise click.ClickException(
                f"{self.deptype.capitalize()} template doesn't support removing all test cases."
            )
        cruft_updated = cruft_update(
            self.target_dir,
            cookiecutter_input=False,
            checkout=self.template_version,
            extra_context=self.cookiecutter_args,
        )
        if not cruft_updated:
            raise click.ClickException("Update from template failed")

        updated = self._commit_or_print_changes(commit, ignore_template_commit)

        if print_completion_message:
            if not commit and updated:
                click.secho(
                    " > User requested to skip committing the rendered changes."
                )

            if updated:
                click.secho(
                    f"{self.deptype.capitalize()} {self.name} successfully updated 🎉",
                    bold=True,
                )
            else:
                click.secho(
                    f"{self.deptype.capitalize()} {self.name} already up-to-date 🎉",
                    bold=True,
                )

        return updated

    def _commit_or_print_changes(
        self, commit: bool, ignore_template_commit: bool
    ) -> bool:
        """Helper for update() which either prints or commits the changes in the
        dependency repo"""
        if not commit:
            diff_text, updated = self.diff(
                ignore_template_commit=ignore_template_commit
            )
            if updated:
                indented = textwrap.indent(diff_text, "     ")
                message = f" > Changes:\n{indented}"
            else:
                message = " > No changes."
            click.echo(message)
        else:
            commit_msg = (
                f"Update from template\n\nTemplate version: {self.template_version}"
            )
            if self.template_commit:
                commit_msg += f" ({self.template_commit[:7]})"

            updated = self.commit(
                commit_msg, init=False, ignore_template_commit=ignore_template_commit
            )

        return updated

    def _stage_all(self, ignore_template_commit: bool = False) -> tuple[str, bool]:
        """Wrapper for GitRepo.stage_all() which stages all changes for a dependency."""
        repo = GitRepo(self.repo_url, self.target_dir, force_init=False)

        diff_func = default_difffunc
        if ignore_template_commit:
            diff_func = _ignore_cruft_json_commit_id
        diff_text, changed = repo.stage_all(
            diff_func=diff_func, ignore_pattern=REJ_IGNORE
        )

        if ignore_template_commit:
            # If we want to ignore updates which only modify the template commit id, we
            # don't use the returned `changed` but instead singal whether there was a
            # change by checking if the diff_text has any contents.
            changed = len(diff_text) > 0

        return diff_text, changed

    def diff(self, ignore_template_commit: bool = False) -> tuple[str, bool]:
        repo = GitRepo(self.repo_url, self.target_dir, force_init=False)
        diff_text, changed = self._stage_all(
            ignore_template_commit=ignore_template_commit
        )

        # When only computing the diff, we reset all staged changes
        repo.reset(working_tree=False)
        return diff_text, changed

    def commit(
        self,
        msg: str,
        amend: bool = False,
        init: bool = True,
        ignore_template_commit: bool = False,
    ) -> bool:
        # If we're amending an existing commit, we don't want to force initialize the
        # repo.
        repo = GitRepo(self.repo_url, self.target_dir, force_init=not amend and init)

        try:
            diff_text, changed = self._stage_all(
                ignore_template_commit=ignore_template_commit
            )
        except MergeConflict as e:
            raise click.ClickException(
                f"Can't commit template changes: merge error in '{e}'. "
                + "Please resolve conflicts and commit manually."
            ) from e

        if changed:
            indented = textwrap.indent(diff_text, "     ")
            message = f" > Changes:\n{indented}"
        else:
            message = " > No changes."
        click.echo(message)

        if changed:
            # Only create a new commit if there are any changes.
            repo.commit(msg, amend=amend)
        return changed
