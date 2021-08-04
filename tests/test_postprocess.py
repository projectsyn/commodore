"""
Tests for postprocessing
"""
import os
import pytest
import yaml

from commodore.config import Config
from commodore.component import Component
from commodore.postprocess import postprocess_components
from test_component_template import test_run_component_new_command


def _make_ns_filter(ns, enabled=None):
    f = {
        "filters": [
            {
                "path": "test",
                "type": "builtin",
                "filter": "helm_namespace",
                "filterargs": {
                    "namespace": ns,
                },
            }
        ]
    }
    if enabled is not None:
        f["filters"][0]["enabled"] = enabled
    return f


def _setup(tmp_path, f, invfilter=False, alias="test-component"):
    test_run_component_new_command(tmp_path=tmp_path)

    targetdir = tmp_path / "compiled" / alias / "test"
    os.makedirs(targetdir, exist_ok=True)
    testf = targetdir / "object.yaml"
    with open(testf, "w") as objf:
        obj = {
            "metadata": {
                "name": "test",
                "namespace": "untouched",
            },
            "kind": "Secret",
            "apiVersion": "v1",
            "stringData": {
                "content": "verysecret",
            },
        }
        yaml.dump(obj, objf)

    # Create external pp filter file
    pp_file = (
        tmp_path / "dependencies" / "test-component" / "postprocess" / "filters.yml"
    )
    os.makedirs(pp_file.parent, exist_ok=True)
    if not invfilter:
        with open(pp_file, "w") as filterf:
            yaml.dump(f, filterf)

    config = Config(work_dir=tmp_path)
    component = Component(
        "test-component", work_dir=tmp_path, repo_url="https://fake.repo.url"
    )
    config.register_component(component)
    aliases = {alias: "test-component"}
    config.register_component_aliases(aliases)
    inventory = {
        alias: {
            "classes": {
                "defaults.test-component",
                "global.common",
                "components.test-component",
            },
            "parameters": {
                "test_component": {
                    "namespace": "syn-test-component",
                },
            },
        },
    }

    if invfilter:
        inventory[alias]["parameters"]["commodore"] = {
            "postprocess": f,
        }

    return testf, config, inventory, config.get_components()


def _expected_ns(enabled):
    if enabled is None or enabled:
        return "myns"
    else:
        return "untouched"


@pytest.mark.parametrize("enabled", [None, True, False])
@pytest.mark.parametrize("invfilter", [True, False])
@pytest.mark.parametrize("alias", ["test-component", "component-alias"])
def test_postprocess_components(tmp_path, capsys, enabled, invfilter, alias):
    f = _make_ns_filter("myns", enabled=enabled)

    testf, config, inventory, components = _setup(
        tmp_path,
        f,
        invfilter=invfilter,
        alias=alias,
    )

    postprocess_components(config, inventory, components)

    assert testf.exists()
    expected_ns = _expected_ns(enabled)
    with open(testf) as objf:
        obj = yaml.safe_load(objf)
        assert obj["metadata"]["namespace"] == expected_ns

    if enabled is not None and not enabled:
        captured = capsys.readouterr()
        assert "Skipping disabled filter" in captured.out


# We keep the enabledref tests separate as we don't actually
# render the inventory with reclass in the test above.
@pytest.mark.parametrize("enabledref", [True, False])
def test_postprocess_components_enabledref(tmp_path, capsys, enabledref):
    f = _make_ns_filter("myns", enabled="${test_component:filter:enabled}")

    testf, config, inventory, components = _setup(tmp_path, f)
    inventory["test-component"]["parameters"]["test_component"]["filter"] = {
        "enabled": enabledref,
    }

    postprocess_components(config, inventory, components)

    assert testf.exists()
    expected_ns = _expected_ns(enabledref)
    with open(testf) as objf:
        obj = yaml.safe_load(objf)
        assert obj["metadata"]["namespace"] == expected_ns

    if enabledref is False:
        captured = capsys.readouterr()
        assert "Skipping disabled filter" in captured.out
