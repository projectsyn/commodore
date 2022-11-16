from __future__ import annotations

import json
import time
import textwrap

from enum import Enum
from pathlib import Path as P
from typing import Any, Iterable, Optional

import click
import jwt
import requests

from url_normalize import url_normalize

from commodore.component import Component, component_parameters_key
from .gitrepo import GitRepo
from .inventory import Inventory
from .multi_dependency import MultiDependency, dependency_key
from .package import Package
from . import tokencache


class Migration(Enum):
    KAP_029_030 = "kapitan-0.29-to-0.30"
    IGNORE_YAML_FORMATTING = "ignore-yaml-formatting"


# pylint: disable=too-many-instance-attributes,too-many-public-methods
class Config:
    _inventory: Inventory
    _components: dict[str, Component]
    _config_repos: dict[str, GitRepo]
    _component_aliases: dict[str, str]
    _packages: dict[str, Package]
    _dependency_repos: dict[str, MultiDependency]
    _deprecation_notices: list[str]
    _migration: Optional[Migration]
    _dynamic_facts: dict[str, Any]
    _github_token: Optional[str]

    oidc_client: Optional[str]
    oidc_discovery_url: Optional[str]

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
        self.api_token = api_token
        self.oidc_client = None
        self.oidc_discovery_url = None
        self._components = {}
        self._config_repos = {}
        self._component_aliases = {}
        self._packages = {}
        self._dependency_repos = {}
        self._verbose = verbose
        self.username = username
        self.usermail = usermail
        self.local = False
        self.push = None
        self.interactive = None
        self.force = False
        self._fetch_dependencies = True
        self._inventory = Inventory(work_dir=self.work_dir)
        self._deprecation_notices = []
        self._global_repo_revision_override = None
        self._tenant_repo_revision_override = None
        self._migration = None
        self._dynamic_facts = {}
        self._github_token = None

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
    def fetch_dependencies(self) -> bool:
        return self._fetch_dependencies

    @fetch_dependencies.setter
    def fetch_dependencies(self, value: bool):
        if not self.local:
            if not value:
                click.secho(
                    "[WARN] --no-fetch-dependencies doesn't take effect "
                    + "unless --local is specified",
                    fg="yellow",
                )
            value = True
        self._fetch_dependencies = value

    @property
    def api_token(self):
        if self._api_token is None and self.api_url:
            tokens = tokencache.get(self.api_url)
            token = tokens.get("id_token")
            if token is not None:
                # We don't verify the signature, we just want to know if the token is expired
                # lieutenant will decide if it's valid
                try:
                    t = jwt.decode(
                        token, algorithms=["RS256"], options={"verify_signature": False}
                    )
                    if "exp" in t and t["exp"] < time.time() + 10:
                        return None
                except jwt.exceptions.InvalidTokenError:
                    return None
                self._api_token = token
        return self._api_token

    @api_token.setter
    def api_token(self, api_token):
        if api_token is not None:
            try:
                p = P(api_token)
                if p.is_file():
                    with open(p, encoding="utf-8") as apitoken:
                        api_token = apitoken.read()
            except OSError as e:
                # File name too long, assume token is not configured as file
                if "File name too long" in e.strerror:
                    pass
                else:
                    raise
            self._api_token = api_token.strip()
        else:
            self._api_token = None

    @property
    def global_repo_revision_override(self):
        return self._global_repo_revision_override

    @global_repo_revision_override.setter
    def global_repo_revision_override(self, rev):
        self._global_repo_revision_override = rev

    @property
    def tenant_repo_revision_override(self):
        return self._tenant_repo_revision_override

    @tenant_repo_revision_override.setter
    def tenant_repo_revision_override(self, rev):
        self._tenant_repo_revision_override = rev

    @property
    def migration(self):
        return self._migration

    @migration.setter
    def migration(self, migration):
        if migration and migration != "":
            self._migration = Migration(migration)

    @property
    def dynamic_facts(self) -> dict[str, Any]:
        """Returns fallback dynamic facts provided on the command line."""
        return self._dynamic_facts

    @dynamic_facts.setter
    def dynamic_facts(self, facts: dict[str, Any]):
        self._dynamic_facts = facts

    @property
    def github_token(self) -> Optional[str]:
        return self._github_token

    @github_token.setter
    def github_token(self, github_token: str):
        self._github_token = github_token

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

    def register_config(self, level, repo: GitRepo):
        self._config_repos[level] = repo

    def get_packages(self) -> dict[str, Package]:
        return self._packages

    def register_package(self, pkg_name: str, pkg: Package):
        self._packages[pkg_name] = pkg

    def register_dependency_repo(self, repo_url: str) -> MultiDependency:
        """Register dependency repository, if it isn't registered yet.

        Returns the `MultiDependency` object for the repo."""
        depkey = dependency_key(repo_url)
        if depkey not in self._dependency_repos:
            self._dependency_repos[depkey] = MultiDependency(
                repo_url,
                self.inventory.dependencies_dir,
                author_name=self.username,
                author_email=self.usermail,
            )

        dep = self._dependency_repos[depkey]
        # Prefer ssh fetch URLs for existing dependencies
        if repo_url.startswith("ssh://"):
            dep.url = repo_url
        return dep

    def get_component_aliases(self):
        return self._component_aliases

    def register_component_aliases(self, aliases: dict[str, str]):
        self._component_aliases = aliases

    def verify_component_aliases(self, cluster_parameters: dict):
        for alias, cn in self._component_aliases.items():
            if alias != cn and not _component_is_aliasable(cluster_parameters, cn):
                raise click.ClickException(
                    f"Component {cn} with alias {alias} does not support instantiation."
                )

    def register_deprecation_notice(self, notice: str):
        self._deprecation_notices.append(notice)

    def print_deprecation_notices(self):
        tw = textwrap.TextWrapper(
            width=100,
            # Next two options ensure we don't break URLs
            break_long_words=False,
            break_on_hyphens=False,
            initial_indent=" > ",
            subsequent_indent="   ",
        )
        if len(self._deprecation_notices) > 0:
            click.secho("\nCommodore notices:", bold=True)
            for notice in self._deprecation_notices:
                notice = tw.fill(notice)
                click.secho(notice)

    def register_component_deprecations(self, cluster_parameters):
        for cname in self._component_aliases.values():
            ckey = component_parameters_key(cname)
            cmeta = cluster_parameters[ckey].get("_metadata", {})

            if cmeta.get("deprecated", False):
                msg = f"Component {cname} is deprecated."
                if "replaced_by" in cmeta:
                    msg += f" Use component {cmeta['replaced_by']} instead."
                if "deprecation_notice" in cmeta:
                    msg += f" {cmeta['deprecation_notice']}"
                self.register_deprecation_notice(msg)

    def discover_oidc_config(self) -> None:
        """Check the configured Lieutenant API URL for OIDC client details, if no OIDC
        client details are given on the command line.

        Update the provided config object in place if the API provides OIDC client
        details."""
        if (
            self.oidc_client is None
            and self.oidc_discovery_url is None
            and self.api_url is not None
        ):
            try:
                r = requests.get(url_normalize(self.api_url))
                api_cfg = json.loads(r.text)
                if "oidc" in api_cfg:
                    self.oidc_client = api_cfg["oidc"].get("clientId")
                    self.oidc_discovery_url = api_cfg["oidc"].get("discoveryUrl")
            except (requests.RequestException, json.JSONDecodeError) as e:
                # We do this on a best effort basis
                click.echo(f" > Unable to auto-discover OIDC config: {e}")


def _component_is_aliasable(cluster_parameters: dict, component_name: str):
    ckey = component_parameters_key(component_name)
    cmeta = cluster_parameters[ckey].get("_metadata", {})
    return cmeta.get("multi_instance", False)


def set_fact_value(facts: dict[str, Any], raw_key: str, value: Any) -> None:
    """Set value for nested fact at `raw_key` (expected form `path.to.key`) to `value`.

    If a segment of the nested key is present in `facts` and not a dictionary or when
    the raw key contains an empty segment, the function won't set a value and will
    instead print a diagnostic message.
    """
    key_parts = raw_key.split(".")

    if any(kp == "" for kp in key_parts):
        # Bail out early if the raw key is malformed (any empty segment)
        click.secho(f"Malformed nested key '{raw_key}' skipping...", fg="yellow")
        return

    prefix_key = ""
    target_dict = facts
    for k in key_parts[:-1]:
        prefix_key = f"{prefix_key}{k}."
        if k in target_dict and not isinstance(target_dict[k], dict):
            click.secho(
                "Trying to insert subkey into non-dictionary "
                + f"dynamic fact '{prefix_key[:-1]}', skipping...",
                fg="yellow",
            )
            return

        target_dict = target_dict.setdefault(k, {})

    key = key_parts[-1]

    if key in target_dict:
        click.secho(
            f"Overwriting dynamic fact '{raw_key}={target_dict[key]}' with '{value}'",
            fg="yellow",
        )
    target_dict[key] = value


def parse_dynamic_fact_value(raw_value: str) -> Any:
    """Parse raw dynamic fact value.

    Tries to parse the value as JSON if it starts with the literal `json:`.

    Returns the parsed value or `None` if trying to parse a JSON value results in a
    decode error."""
    if raw_value.startswith("json:"):
        json_val = raw_value.replace("json:", "", 1)
        # Parse value as JSON if it starts with `json:`, skip value completely
        # on parse errors.
        try:
            v = json.loads(json_val)
        except json.JSONDecodeError as e:
            click.secho(
                f"Expected value '{json_val}' to be parsable JSON, "
                + f"but parsing failed with '{e}', skipping",
                fg="yellow",
            )
            return None
    else:
        v = raw_value
    return v


def parse_dynamic_facts_from_cli(raw_facts: Iterable[str]) -> dict[str, Any]:
    """Parse dynamic facts dictionary from strings provided on command line.

    The function expects each raw fact (string) to be of the form `key=value`, where key
    can contain dots to specify nested keys (e.g. `path.to.key`), and value is parsed as
    JSON when it starts with the literal `json:`.

    Inputs are processed in order, and subsequent inputs setting the same key will
    overwrite any existing values. Facts for nested keys will be skipped, if a parent
    key already exists *and* isn't a dictionary.

    Facts with values marked as JSON which result in a decode error will be skipped.

    Returns a dict with the parsed dynamic facts structure.
    """
    facts: dict[str, Any] = {}

    for f in raw_facts:
        if "=" not in f:
            click.secho(
                f"Ignoring dynamic fact {f} which is not in format key=value",
                fg="yellow",
            )
            continue
        raw_key, raw_value = f.split("=", maxsplit=1)
        if not raw_key:
            click.secho(
                f"Ignoring malformed dynamic fact '{f}' with no key.", fg="yellow"
            )
            continue
        if not raw_value:
            click.secho(
                f"Ignoring malformed dynamic fact '{f}' with no value. "
                + "Please specify empty string value as 'json:\"\"'",
                fg="yellow",
            )
            continue

        # Parse value first, so we never add empty dicts for a nested key whose JSON
        # value turns out to be malformed.
        value = parse_dynamic_fact_value(raw_value)
        if value is None:
            # skip when we failed to parse a value that identified itself as JSON
            continue

        set_fact_value(facts, raw_key, value)

    return facts
