from __future__ import annotations

from pathlib import Path as P
from typing import Any, Callable, ClassVar, Protocol

import click

from commodore.config import Config, Component

from .jsonnet import run_jsonnet_filter, validate_jsonnet_filter
from .builtin_filters import run_builtin_filter, validate_builtin_filter


class FilterFunc(Protocol):
    # pylint: disable=too-many-arguments
    def __call__(
        self,
        config: Config,
        inv: dict,
        component: Component,
        instance: str,
        filterid: str,
        path: P,
        **filterargs: str,
    ):
        ...


ValidateFunc = Callable[[Config, Component, str, dict], dict]


class Filter:
    type: str
    filter: str
    path: P
    filterargs: dict
    enabled: bool

    # PyLint complains about ClassVar not being subscriptable
    # pylint: disable=unsubscriptable-object
    _run_handlers: ClassVar[dict[str, FilterFunc]] = {
        "builtin": run_builtin_filter,
        "jsonnet": run_jsonnet_filter,
    }
    # pylint: disable=unsubscriptable-object
    _validate_handlers: ClassVar[dict[str, ValidateFunc]] = {
        "builtin": validate_builtin_filter,
        "jsonnet": validate_jsonnet_filter,
    }
    # pylint: disable=unsubscriptable-object
    _required_keys: ClassVar[set[str]] = {"type", "path", "filter"}

    def __init__(self, fd: dict):
        """
        Assumes that `fd` has been validated with `_validate_filter`.
        """
        self.type = fd["type"]
        self.filter = fd["filter"]
        self.path = P(fd["path"])
        self.enabled = fd.get("enabled", True)
        self.filterargs = fd.get("filterargs", {})
        self._runner: FilterFunc = self._run_handlers[self.type]

    def run(self, config: Config, inventory: dict, component: Component, instance: str):
        """
        Run the filter.
        """
        if not self.enabled:
            click.secho(
                f" > Skipping disabled filter {self.filter} on path {self.path}"
            )
            return

        self._runner(
            config,
            inventory,
            component,
            instance,
            self.filter,
            self.path,
            **self.filterargs,
        )

    @classmethod
    def validate(cls, config: Config, c: Component, instance: str, f: dict):
        """
        Validate filter definition in `f`.
        Raises exceptions as appropriate when the definition is invalid.
        Returns the definiton if it validates successfully.
        """
        if not all(key in f for key in cls._required_keys):
            missing_required_keys = cls._required_keys - f.keys()
            raise KeyError(f"Filter is missing required key(s) {missing_required_keys}")

        if "enabled" in f and not isinstance(f["enabled"], bool):
            raise ValueError("Filter key 'enabled' is not a boolean")

        typ = f["type"]
        if typ not in cls._validate_handlers:
            raise ValueError(f"Filter has unknown type {typ}")

        # perform type-specific extra validation
        cls._validate_handlers[typ](config, c, instance, f)

        return f

    @classmethod
    def from_dict(cls, config: Config, c: Component, instance: str, f: dict):
        """
        Create Filter object from filter definition dict `f`.
        Raises exceptions as appropriate when the definition is invalid.
        Returns a Filter object if the passed definition validates successfully.
        """
        return Filter(Filter.validate(config, c, instance, f))


def _get_inventory_filters(inv: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Return list of filters defined in inventory.

    Inventory filters are expected to be defined as a list in
    `parameters.commodore.postprocess.filters`.
    """
    commodore = inv["parameters"].get("commodore", {})
    return commodore.get("postprocess", {}).get("filters", [])


def postprocess_components(
    config: Config,
    kapitan_inventory: dict[str, dict[str, Any]],
    components: dict[str, Component],
):
    click.secho("Postprocessing...", bold=True)

    aliases = config.get_component_aliases()

    for a, cn in aliases.items():
        c = components[cn]
        inv = kapitan_inventory.get(a)
        if not inv:
            click.echo(f" > No target exists for component {cn}, skipping...")
            continue

        # inventory filters
        invfilters = _get_inventory_filters(inv)

        filters: list[Filter] = []
        for fd in invfilters:
            try:
                filters.append(Filter.from_dict(config, c, a, fd))
            except (KeyError, ValueError) as e:
                filtername = fd.get("filter", "<unknown>")
                click.secho(
                    f" > Skipping filter '{filtername}' with invalid definition {fd}: {e}",
                    fg="yellow",
                )

        if len(filters) > 0 and config.debug:
            click.echo(f" > {cn}...")

        for f in filters:
            if config.debug:
                click.secho(f"   > Executing filter '{f.type}:{f.filter}'")
            f.run(config, inv, c, a)
