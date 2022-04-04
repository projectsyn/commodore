from pathlib import Path as P
from typing import Any, Callable, ClassVar, Dict, List, Set
from typing_extensions import Protocol

import click

from commodore.config import Config, Component
from commodore.helpers import yaml_load

from .inventory import resolve_inventory_vars, InventoryError

from .jsonnet import run_jsonnet_filter, validate_jsonnet_filter
from .builtin_filters import run_builtin_filter, validate_builtin_filter


class FilterFunc(Protocol):
    # pylint: disable=too-many-arguments
    def __call__(
        self,
        config: Config,
        inv: Dict,
        component: Component,
        instance: str,
        filterid: str,
        path: P,
        **filterargs: str,
    ):
        ...


ValidateFunc = Callable[[Config, Component, str, Dict], Dict]


class Filter:
    type: str
    filter: str
    path: P
    filterargs: Dict
    enabled: bool

    # PyLint complains about ClassVar not being subscriptable
    # pylint: disable=unsubscriptable-object
    _run_handlers: ClassVar[Dict[str, FilterFunc]] = {
        "builtin": run_builtin_filter,
        "jsonnet": run_jsonnet_filter,
    }
    # pylint: disable=unsubscriptable-object
    _validate_handlers: ClassVar[Dict[str, ValidateFunc]] = {
        "builtin": validate_builtin_filter,
        "jsonnet": validate_jsonnet_filter,
    }
    # pylint: disable=unsubscriptable-object
    _required_keys: ClassVar[Set[str]] = {"type", "path", "filter"}

    def __init__(self, fd: Dict):
        """
        Assumes that `fd` has been validated with `_validate_filter`.
        """
        self.type = fd["type"]
        self.filter = fd["filter"]
        self.path = P(fd["path"])
        self.enabled = fd.get("enabled", True)
        self.filterargs = fd.get("filterargs", {})
        self._runner: FilterFunc = self._run_handlers[self.type]

    def run(self, config: Config, inventory: Dict, component: Component, instance: str):
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
    def validate(cls, config: Config, c: Component, instance: str, f: Dict):
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
    def from_dict(cls, config: Config, c: Component, instance: str, f: Dict):
        """
        Create Filter object from filter definition dict `f`.
        Raises exceptions as appropriate when the definition is invalid.
        Returns a Filter object if the passed definition validates successfully.
        """
        return Filter(Filter.validate(config, c, instance, f))


def _get_inventory_filters(inv: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Return list of filters defined in inventory.

    Inventory filters are expected to be defined as a list in
    `parameters.commodore.postprocess.filters`.
    """
    commodore = inv["parameters"].get("commodore", {})
    return commodore.get("postprocess", {}).get("filters", [])


def _get_external_filters(inv: Dict[str, Any], c: Component) -> List[Dict[str, Any]]:
    filters_file = c.filters_file
    filters = []
    if filters_file.is_file():
        _filters = yaml_load(filters_file).get("filters", [])
        for f in _filters:
            # Resolve any inventory references in filter definition
            try:
                f = resolve_inventory_vars(inv, f)
            except InventoryError as e:
                raise click.ClickException(
                    f"Failed to resolve reclass references for external filter: {e}"
                ) from e

            # external filters without 'type' always have type 'jsonnet'
            if "type" not in f:
                click.secho(
                    "   > [WARN] component uses untyped external postprocessing filter",
                    fg="yellow",
                )
                f["type"] = "jsonnet"

            if f["type"] == "jsonnet":
                f["path"] = f["output_path"]
                del f["output_path"]
                f["filter"] = str(P("postprocess") / f["filter"])
            filters.append(f)

    return filters


def postprocess_components(
    config: Config,
    kapitan_inventory: Dict[str, Dict[str, Any]],
    components: Dict[str, Component],
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

        # "old", external filters
        extfilters = _get_external_filters(inv, c)
        if len(extfilters) > 0:
            deprecation_notice_url = (
                "https://syn.tools/commodore/reference/"
                + "deprecation-notices.html#_external_pp_filters"
            )
            config.register_deprecation_notice(
                f"Component '{c.name}' uses deprecated external postprocessing "
                + f"filter definitions. See {deprecation_notice_url} for more details."
            )

        filters: List[Filter] = []
        for fd in invfilters + extfilters:
            try:
                filters.append(Filter.from_dict(config, c, a, fd))
            except (KeyError, ValueError) as e:
                click.secho(
                    f" > Skipping filter '{fd['filter']}' with invalid definition {fd}: {e}",
                    fg="yellow",
                )

        if len(filters) > 0 and config.debug:
            click.echo(f" > {cn}...")

        for f in filters:
            if config.debug:
                click.secho(f"   > Executing filter '{f.type}:{f.filter}'")
            f.run(config, inv, c, a)
