from __future__ import annotations

from unittest.mock import patch

import click
import pytest

from test_dependency_mgmt import _setup_mock_inventory

from commodore.config import Config

from commodore.dependency_mgmt import discovery


@pytest.mark.parametrize(
    "expected_aliases,expected_exception_msg",
    [
        (
            {"other-component": "aliased", "third-component": "aliased"},
            "Duplicate component alias 'aliased': components "
            + "'other-component' and 'third-component' are aliased to 'aliased'",
        ),
        (
            {"other-component": "third-component", "third-component": "aliased"},
            "Component 'other-component' aliases existing component 'third-component'",
        ),
        (
            {
                "test-component": "third-component",
                "other-component": "third-component",
                "third-component": "aliased",
            },
            "Components 'other-component' and 'test-component' alias "
            + "existing component 'third-component'",
        ),
    ],
)
@patch.object(discovery, "kapitan_inventory")
def test_discover_components_duplicate_aliases(
    patch_inventory, config: Config, expected_aliases, expected_exception_msg
):
    _setup_mock_inventory(patch_inventory, expected_aliases)

    with pytest.raises(KeyError) as e:
        discovery._discover_components(config)

    assert e.value.args[0] == expected_exception_msg


@patch.object(discovery, "kapitan_inventory")
@pytest.mark.parametrize("packages", [[], ["test"]])
def test_discover_components(patch_inventory, config: Config, packages):
    component_inv = _setup_mock_inventory(patch_inventory, packages=packages)

    components, aliases = discovery._discover_components(config)
    assert components == sorted(component_inv.keys())
    assert sorted(aliases.keys()) == components
    assert all(k == v for k, v in aliases.items())
    assert all(p not in aliases.keys() and p not in aliases.values() for p in packages)


@patch.object(discovery, "kapitan_inventory")
def test_discover_components_aliases(patch_inventory, config: Config):
    expected_aliases = {"other-component": "aliased"}
    component_inv = _setup_mock_inventory(patch_inventory, expected_aliases)

    components, aliases = discovery._discover_components(config)
    assert components == sorted(component_inv.keys())
    assert set(components + list(expected_aliases.values())) == set(aliases.keys())
    assert set(aliases.values()) == set(components)
    assert aliases["aliased"] == "other-component"


@patch.object(discovery, "kapitan_inventory")
@pytest.mark.parametrize(
    "packages", [[], ["test"], ["test", "foo"], ["test", "test-component"]]
)
def test_discover_packages(patch_inventory, config: Config, packages: list[str]):
    component_inv = _setup_mock_inventory(patch_inventory, packages=packages)

    pkgs = discovery._discover_packages(config)
    assert sorted(packages) == sorted(pkgs)
    non_overlap = set(component_inv.keys()) - set(packages)
    assert all(cn not in pkgs for cn in non_overlap)


@patch.object(discovery, "kapitan_inventory")
@pytest.mark.parametrize(
    "packages,expected",
    [
        (
            ["t-foo"],
            "Package names can't be prefixed with 't-'. "
            + "This prefix is reserved for tenant configurations.",
        ),
        (["components"], "Can't use reserved name 'components' as package name"),
        (["defaults"], "Can't use reserved name 'defaults' as package name"),
        (["global"], "Can't use reserved name 'global' as package name"),
        (["params"], "Can't use reserved name 'params' as package name"),
    ],
)
def test_discover_packages_illegal(
    patch_inventory, config: Config, packages: list[str], expected: str
):
    _ = _setup_mock_inventory(patch_inventory, packages=packages)

    with pytest.raises(click.ClickException) as e:
        _ = discovery._discover_packages(config)

    assert expected in str(e.value)
