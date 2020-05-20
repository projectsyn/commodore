import re
import os
from base64 import b64encode
from pathlib import Path as P

import click

from .helpers import rm_tree_contents, yaml_dump


class SecretRef:
    """
    Helper class for finding Kapitan secret ref strings and producing Kapitan
    secret ref files
    """
    _SECRET_REF = re.compile(r'\?{([^}]+)\}')

    def __init__(self, key, ref):
        self.keys = [key]
        refelems = ref.split(':')
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
        if self.type == 'vaultkv':
            secret, key = self.ref.rsplit('/', 1)
            return b64encode(f"{secret}:{key}".encode()).decode('utf-8')

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
        if self.type != 'vaultkv':
            raise NotImplementedError(f"ref type: {self.type}")
        params = ref_params[self.type]
        refdef = {
            'data': self._mangle_ref(),
            'encoding': 'original',
            'type': self.type,
            params['key']: params['values'],
        }
        os.makedirs(reffile.parent, exist_ok=True)
        yaml_dump(refdef, reffile)

    def add_key(self, key):
        self.keys.append(key)


class RefBuilder:
    """
    Helper class to wrap recursive search for Kapitan secret references
    """

    def __init__(self, debug, parameters):
        self.debug = debug
        self.parameters = parameters
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
                    if self.debug:
                        click.echo('    > Duplicate ref, adding key to list')
                    self._refs[r.refstr].add_key(key)
                else:
                    self._refs[r.refstr] = r
        elif self.debug:
            click.echo(f"    > Ignoring leaf of type {type(value).__name__}...")

    def _find_refs(self, prefix, params):
        """
        Recursively search Kapitan refs, descending into dicts and lists.
        """
        if self.debug:
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

    def find_refs(self):
        """
        Search for Kapitan secret refs in `self.parameters`
        """
        self._find_refs('', self.parameters)

    @property
    def refs(self):
        return self._refs.values()

    @property
    def params(self):
        if self._ref_params is None:
            kapitan_params = self.parameters['kapitan']['secrets']['vaultkv']
            self._ref_params = {
                'vaultkv': {
                    'key': 'vault_params',
                    'values': kapitan_params
                }
            }
        return self._ref_params


def update_refs(config, parameters):
    """
    Iterate over parameters dict, and create Kapitan secret refs for all
    ?{...} found as values in the dict
    """
    click.secho("Updating Kapitan secret references...", bold=True)
    refdir = P('catalog', 'refs')
    os.makedirs(refdir, exist_ok=True)
    rm_tree_contents(refdir)
    # Find references
    rb = RefBuilder(config.debug, parameters)
    rb.find_refs()
    ref_params = rb.params
    # Create Kapitan references
    for r in rb.refs:
        if config.debug:
            click.echo(f" > Creating Kapitan reffile for secret ref {r.refstr}")
        r.create_kapitan_ref(refdir, ref_params, debug=config.debug)
