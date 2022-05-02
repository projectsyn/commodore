from __future__ import annotations

from unittest.mock import patch
from pathlib import Path

import click
import pytest

from test_dependency_mgmt import _setup_mock_inventory, data

from commodore.config import Config

from commodore.dependency_mgmt import version_parsing


@patch.object(version_parsing, "kapitan_inventory")
def test_read_components(patch_inventory, data: Config):
    components = _setup_mock_inventory(patch_inventory)
    component_urls, component_versions = version_parsing._read_components(
        data, ["test-component"]
    )

    # check that exactly 'test-component' is discovered
    assert {"test-component"} == set(component_urls.keys())
    assert components["test-component"]["url"] == component_urls["test-component"]
    assert (
        components["test-component"]["version"] == component_versions["test-component"]
    )


@patch.object(version_parsing, "kapitan_inventory")
def test_read_components_multiple(patch_inventory, data: Config):
    components = _setup_mock_inventory(patch_inventory)
    component_urls, component_versions = version_parsing._read_components(
        data, components.keys()
    )
    # check that exactly 'test-component' is discovered
    assert set(components.keys()) == set(component_urls.keys())
    assert set(components.keys()) == set(component_versions.keys())
    assert all(components[cn]["url"] == component_urls[cn] for cn in components.keys())
    assert all(
        components[cn].get("version", None) == component_versions[cn]
        for cn in components.keys()
    )


@patch.object(version_parsing, "kapitan_inventory")
def test_read_components_exception(
    patch_inventory, data: Config, tmp_path: Path, capsys
):
    components = _setup_mock_inventory(patch_inventory, omit_version=True)

    with pytest.raises(click.ClickException) as e:
        _ = version_parsing._read_components(data, components.keys())

    assert "Component 'other-component' doesn't have a version specified" in str(
        e.value
    )


@pytest.mark.parametrize(
    "components,ckeys,exctext",
    [
        ({}, [], "Component list ('parameters.components') missing"),
        (
            {"components": {"a": {"url": "a_url"}}},
            ["b"],
            "Unknown component 'b'. Please add it to 'parameters.components'",
        ),
        (
            {"components": {"a": {"version": "a_version"}}},
            ["a"],
            "No url for component 'a' configured",
        ),
    ],
)
@patch.object(version_parsing, "kapitan_inventory")
def test_read_components_exc(
    patch_inventory,
    data: Config,
    tmp_path: Path,
    capsys,
    components,
    ckeys,
    exctext,
):
    patch_inventory.return_value = {
        data.inventory.bootstrap_target: {"parameters": components},
    }

    with pytest.raises(click.ClickException) as exc_info:
        _ = version_parsing._read_components(data, ckeys)

    assert exc_info.value.args[0] == exctext
