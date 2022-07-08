"""
Tests for dependency management inventory version parsing.

We test most cases in `_read_versions()` through `_read_components()` tests, as the
functionality of `_read_versions()` was originally implemented directly in
`_read_components()`.
"""
from __future__ import annotations

from unittest.mock import patch
from pathlib import Path

import click
import pytest

from test_dependency_mgmt import _setup_mock_inventory

from commodore.config import Config

from commodore.dependency_mgmt import version_parsing


@patch.object(version_parsing, "kapitan_inventory")
def test_read_components(patch_inventory, config: Config):
    components = _setup_mock_inventory(patch_inventory)
    cspecs = version_parsing._read_components(config, ["test-component"])

    # check that exactly 'test-component' is discovered
    assert {"test-component"} == set(cspecs.keys())
    assert components["test-component"]["url"] == cspecs["test-component"].url
    assert components["test-component"]["version"] == cspecs["test-component"].version


@patch.object(version_parsing, "kapitan_inventory")
def test_read_components_multiple(patch_inventory, config: Config):
    components = _setup_mock_inventory(patch_inventory)
    cspecs = version_parsing._read_components(config, components.keys())
    # check that exactly 'test-component' is discovered
    assert set(components.keys()) == set(cspecs.keys())
    assert all(components[cn]["url"] == cspecs[cn].url for cn in components.keys())
    assert all(
        components[cn].get("version", None) == cspecs[cn].version
        for cn in components.keys()
    )


@patch.object(version_parsing, "kapitan_inventory")
def test_read_components_exception(
    patch_inventory, config: Config, tmp_path: Path, capsys
):
    components = _setup_mock_inventory(patch_inventory, omit_version=True)

    with pytest.raises(click.ClickException) as e:
        _ = version_parsing._read_components(config, components.keys())

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
    config: Config,
    tmp_path: Path,
    capsys,
    components,
    ckeys,
    exctext,
):
    patch_inventory.return_value = {
        config.inventory.bootstrap_target: {"parameters": components},
    }

    with pytest.raises(click.ClickException) as exc_info:
        _ = version_parsing._read_components(config, ckeys)

    assert exc_info.value.args[0] == exctext


params_packages = {
    "packages": {
        "test": {
            "url": "https://git.example.com/pkg.git",
            "version": "v1.0.0",
        },
        "foo": {
            "url": "https://git.example.com/foo.git",
            "version": "feat/initial",
        },
    }
}


@patch.object(version_parsing, "kapitan_inventory")
@pytest.mark.parametrize(
    "params,pkg_names,expected_urls,expected_versions",
    [
        ({}, [], {}, {}),
        (
            params_packages,
            ["test"],
            {"test": "https://git.example.com/pkg.git"},
            {"test": "v1.0.0"},
        ),
        (
            params_packages,
            ["test", "foo"],
            {
                "test": "https://git.example.com/pkg.git",
                "foo": "https://git.example.com/foo.git",
            },
            {"test": "v1.0.0", "foo": "feat/initial"},
        ),
    ],
)
def test_read_packages(
    patch_inventory,
    config: Config,
    params: dict,
    pkg_names: list[str],
    expected_urls: dict,
    expected_versions: dict,
):
    patch_inventory.return_value = {
        config.inventory.bootstrap_target: {
            "parameters": params,
        }
    }

    pspecs = version_parsing._read_packages(
        config,
        pkg_names,
    )
    pkg_urls = {}
    pkg_versions = {}
    for p, pspec in pspecs.items():
        pkg_urls[p] = pspec.url
        pkg_versions[p] = pspec.version
    assert pkg_urls == expected_urls
    assert pkg_versions == expected_versions
