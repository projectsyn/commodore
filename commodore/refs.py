from __future__ import annotations

import re
import os
from base64 import b64encode
from pathlib import Path as P

import click

from .component import component_parameters_key
from .config import Config
from .helpers import rm_tree_contents, yaml_dump


class SecretRef:
    """
    Helper class for finding Kapitan secret ref strings and producing Kapitan
    secret ref files
    """

    _SECRET_REF = re.compile(r"\?{([^}]+)\}")

    def __init__(self, key, ref):
        self.keys = [key]
        refelems = ref.split(":")
        self.type = refelems[0]
        self.ref = refelems[1]

    def __str__(self):
        return f"SecretRef(invkeys={self.keys}, type={self.type}, ref={self.ref})"

    @property
    def refstr(self):
        return f"{self.type}:{self.ref}"

    @classmethod
    def from_value(cls, key, value):
        """
        Create SecretRef object from string `value`, if the string contains a
        Kapitan secret reference. If no secret reference is contained in
        `value` this method returns None.
        """
        m = cls._SECRET_REF.search(value)
        if m:
            return SecretRef(key, m.group(1))

        return None

    def _mangle_ref(self):
        """
        Transform Kapitan secret reference into base64 encoded reference for
        kapitan refs --reveal. This method replaces one part of what
        `kapitan refs --write` would do.

        Currently only `vaultkv` references are supported.
        """
        if self.type == "vaultkv":
            secret, key = self.ref.rsplit("/", 1)
            return b64encode(f"{secret}:{key}".encode()).decode("utf-8")

        raise NotImplementedError(f"Ref type: {self.type}")

    def create_kapitan_ref(self, refdir, ref_params, debug=False):
        """
        Create a Kapitan secret ref file from this reference.

        This method creates a secret ref file in `refdir` which Kapitan can
        subsequently use for revealing the secret.

        Currently only `vaultkv` references are supported.
        """
        reffile = P(refdir, self.ref)
        if debug:
            click.echo(f"    > Writing to file {reffile}")
        if self.type != "vaultkv":
            raise NotImplementedError(f"ref type: {self.type}")
        params = ref_params[self.type]
        refdef = {
            "data": self._mangle_ref(),
            "encoding": "original",
            "type": self.type,
            params["key"]: params["values"],
        }
        os.makedirs(reffile.parent, exist_ok=True)
        yaml_dump(refdef, reffile)

    def add_key(self, key):
        self.keys.append(key)


class RefBuilder:
    """
    Helper class to wrap recursive search for Kapitan secret references
    """

    _refs: dict[str, SecretRef]

    def __init__(self, config: Config, inventory):
        self.debug = config.debug
        self.trace = config.trace
        self._bootstrap_target = config.inventory.bootstrap_target
        self.inventory = inventory
        self._refs = {}
        self._ref_params = None

    def _find_ref(self, key, value):
        """
        Process leaf value of parameters structure.
        """
        # Only consider leaves which are of type string, other types cannot
        # contain a secret reference.
        if isinstance(value, str):
            r = SecretRef.from_value(key, value)
            if r is not None:
                if self.debug:
                    click.echo(f"    > Found secret ref {r.refstr} in {value}")
                if r.refstr in self._refs:
                    if self.trace:
                        click.echo("    > Duplicate ref, adding key to list")
                    self._refs[r.refstr].add_key(key)
                else:
                    self._refs[r.refstr] = r
        elif self.trace:
            click.echo(f"    > Ignoring leaf of type {type(value).__name__}...")

    def _find_refs(self, prefix, params):
        """
        Recursively search Kapitan refs, descending into dicts and lists.
        """
        if self.trace:
            click.echo(f" > Processing {prefix}")

        if isinstance(params, dict):
            # Recurse for dicts
            for k, v in params.items():
                self._find_refs(f"{prefix}/{k}", v)
        elif isinstance(params, list):
            # Recurse for lists
            for idx, e in enumerate(params):
                self._find_refs(f"{prefix}[{idx}]", e)
        else:
            # Otherwise, handle as leaf
            self._find_ref(prefix, params)

    def find_refs(self, target: str, key: str):
        """
        Search for Kapitan secret refs in key `key` in the parameters for
        Kapitan target `target`.
        """
        params = self.inventory[target]["parameters"][key]
        self._find_refs(key, params)

    @property
    def refs(self):
        return self._refs.values()

    @property
    def params(self):
        if self._ref_params is None:
            kapitan_params = self.inventory[self._bootstrap_target]["parameters"][
                "kapitan"
            ]["secrets"]["vaultkv"]
            self._ref_params = {
                "vaultkv": {"key": "vault_params", "values": kapitan_params}
            }
        return self._ref_params


def update_refs(config: Config, aliases: dict[str, str], inventory: dict):
    """
    Iterate over parameters for each target, and create Kapitan secret refs
    for all ?{...} found as values in the dicts
    """
    click.secho("Updating Kapitan secret references...", bold=True)
    os.makedirs(config.refs_dir, exist_ok=True)
    rm_tree_contents(config.refs_dir)

    rb = RefBuilder(config, inventory)

    # Generate list of component keys from component aliases dict
    component_keys = set(map(component_parameters_key, aliases.values()))
    bootstrap_target = config.inventory.bootstrap_target
    # Find all keys in the bootstrap target's parameters which don't directly
    # belong to a component.
    non_component_keys = (
        set(inventory[bootstrap_target]["parameters"].keys()) - component_keys
    )
    # Search those keys in the bootstrap target for secret references
    for key in non_component_keys:
        rb.find_refs(bootstrap_target, key)

    for target, component in aliases.items():
        # For components, any dashes in the component name are replaced by
        # underscores in the parameters key.
        component_key = component_parameters_key(component)
        # Find references for component instance
        rb.find_refs(target, component_key)

    ref_params = rb.params
    # Create Kapitan references
    for r in rb.refs:
        if config.debug:
            click.echo(f" > Creating Kapitan reffile for secret ref {r.refstr}")
        r.create_kapitan_ref(config.refs_dir, ref_params, debug=config.debug)
