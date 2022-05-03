from unittest.mock import patch

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
def test_discover_components(patch_inventory, config: Config):
    component_inv = _setup_mock_inventory(patch_inventory)

    components, aliases = discovery._discover_components(config)
    assert components == sorted(component_inv.keys())
    assert sorted(aliases.keys()) == components
    assert all(k == v for k, v in aliases.items())


@patch.object(discovery, "kapitan_inventory")
def test_discover_components_aliases(patch_inventory, config: Config):
    expected_aliases = {"other-component": "aliased"}
    component_inv = _setup_mock_inventory(patch_inventory, expected_aliases)

    components, aliases = discovery._discover_components(config)
    assert components == sorted(component_inv.keys())
    assert set(components + list(expected_aliases.values())) == set(aliases.keys())
    assert set(aliases.values()) == set(components)
    assert aliases["aliased"] == "other-component"
