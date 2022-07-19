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
    cspecs = version_parsing._read_components(
        config, {"test-component": "test-component"}
    )

    # check that exactly 'test-component' is discovered
    assert {"test-component"} == set(cspecs.keys())
    assert components["test-component"]["url"] == cspecs["test-component"].url
    assert components["test-component"]["version"] == cspecs["test-component"].version


@patch.object(version_parsing, "kapitan_inventory")
def test_read_components_multiple(patch_inventory, config: Config):
    components = _setup_mock_inventory(patch_inventory)
    cspecs = version_parsing._read_components(config, {k: k for k in components.keys()})
    # check that exactly 'test-component' is discovered
    assert set(components.keys()) == set(cspecs.keys())
    assert all(components[cn]["url"] == cspecs[cn].url for cn in components.keys())
    assert all(
        components[cn].get("version", None) == cspecs[cn].version
        for cn in components.keys()
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
            "Component 'a' is missing field 'url'",
        ),
        (
            {"components": {"a": {"url": "a_url"}}},
            ["a"],
            "Component 'a' is missing field 'version'",
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
        _ = version_parsing._read_components(config, {k: k for k in ckeys})

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
        "bar": {
            "url": "https://git.example.com/barbaz.git",
            "version": "master",
            "path": "bar",
        },
        "baz": {
            "url": "https://git.example.com/barbaz.git",
            "version": "master",
            "path": "/baz",
        },
    }
}


@patch.object(version_parsing, "kapitan_inventory")
@pytest.mark.parametrize(
    "params,pkg_names,expected",
    [
        ({}, [], {}),
        (
            params_packages,
            ["test"],
            {
                "test": version_parsing.DependencySpec(
                    "https://git.example.com/pkg.git", "v1.0.0", ""
                ),
            },
        ),
        (
            params_packages,
            ["test", "foo"],
            {
                "test": version_parsing.DependencySpec(
                    "https://git.example.com/pkg.git", "v1.0.0", ""
                ),
                "foo": version_parsing.DependencySpec(
                    "https://git.example.com/foo.git", "feat/initial", ""
                ),
            },
        ),
        (
            params_packages,
            ["test", "foo", "bar", "baz"],
            {
                "test": version_parsing.DependencySpec(
                    "https://git.example.com/pkg.git", "v1.0.0", ""
                ),
                "foo": version_parsing.DependencySpec(
                    "https://git.example.com/foo.git", "feat/initial", ""
                ),
                "bar": version_parsing.DependencySpec(
                    "https://git.example.com/barbaz.git", "master", "bar"
                ),
                "baz": version_parsing.DependencySpec(
                    "https://git.example.com/barbaz.git", "master", "baz"
                ),
            },
        ),
    ],
)
def test_read_packages(
    patch_inventory,
    config: Config,
    params: dict,
    pkg_names: list[str],
    expected: dict[str, version_parsing.DependencySpec],
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
    assert pspecs == expected
