"""
Tests for postprocessing
"""
import os
import yaml
from commodore.config import Config
from commodore.component import Component
from commodore.postprocess import postprocess_components
from test_component_template import test_run_component_new_command


def _make_ns_filter(ns, enabled=None):
    filter = {
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
        filter["filters"][0]["enabled"] = enabled
    return filter


def _setup(
    tmp_path, filter, invfilter=False, alias="test-component", aliased_output=False
):
    test_run_component_new_command(tmp_path=tmp_path)

    targetdir = "test-component"
    if aliased_output:
        targetdir = alias

    targetdir = tmp_path / "compiled" / targetdir / "test"
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
            yaml.dump(filter, filterf)

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
            "postprocess": filter,
        }

    return testf, config, inventory, config.get_components()


def test_postprocess_components(tmp_path, capsys):
    filter = _make_ns_filter("myns")
    testf, config, inventory, components = _setup(tmp_path, filter)
    config.update_verbosity(3)
    print(testf)
    print(testf.resolve())
    postprocess_components(config, inventory, components)
    assert testf.exists()
    with open(testf) as objf:
        obj = yaml.safe_load(objf)
        assert obj["metadata"]["namespace"] == "myns"


def test_postprocess_components_enabled(tmp_path, capsys):
    filter = _make_ns_filter("myns", enabled=True)
    testf, config, inventory, components = _setup(tmp_path, filter)
    postprocess_components(config, inventory, components)
    assert testf.exists()
    with open(testf) as objf:
        obj = yaml.safe_load(objf)
        assert obj["metadata"]["namespace"] == "myns"


def test_postprocess_components_disabled(tmp_path, capsys):
    filter = _make_ns_filter("myns", enabled=False)
    testf, config, inventory, components = _setup(tmp_path, filter)
    postprocess_components(config, inventory, components)
    assert testf.exists()
    with open(testf) as objf:
        obj = yaml.safe_load(objf)
        assert obj["metadata"]["namespace"] == "untouched"
    captured = capsys.readouterr()
    assert "Skipping disabled filter" in captured.out


def test_postprocess_components_enabledref(tmp_path, capsys):
    filter = _make_ns_filter("myns", enabled="${test_component:filter:enabled}")
    testf, config, inventory, components = _setup(tmp_path, filter)
    inventory["test-component"]["parameters"]["test_component"]["filter"] = {
        "enabled": True,
    }
    postprocess_components(config, inventory, components)
    assert testf.exists()
    with open(testf) as objf:
        obj = yaml.safe_load(objf)
        assert obj["metadata"]["namespace"] == "myns"


def test_postprocess_components_disabledref(tmp_path, capsys):
    filter = _make_ns_filter("myns", enabled="${test_component:filter:enabled}")
    testf, config, inventory, components = _setup(tmp_path, filter)
    inventory["test-component"]["parameters"]["test_component"]["filter"] = {
        "enabled": False,
    }
    postprocess_components(config, inventory, components)
    assert testf.exists()
    with open(testf) as objf:
        obj = yaml.safe_load(objf)
        assert obj["metadata"]["namespace"] == "untouched"
    captured = capsys.readouterr()
    assert "Skipping disabled filter" in captured.out


def test_postprocess_components_invfilter(tmp_path, capsys):
    f = _make_ns_filter("myns")
    testf, config, inventory, components = _setup(tmp_path, f, invfilter=True)
    postprocess_components(config, inventory, components)
    assert testf.exists()
    with open(testf) as objf:
        obj = yaml.safe_load(objf)
        assert obj["metadata"]["namespace"] == "myns"


def test_postprocess_components_invfilter_explicit_enabled(tmp_path, capsys):
    f = _make_ns_filter("myns", enabled=True)
    testf, config, inventory, components = _setup(tmp_path, f, invfilter=True)
    postprocess_components(config, inventory, components)
    assert testf.exists()
    with open(testf) as objf:
        obj = yaml.safe_load(objf)
        assert obj["metadata"]["namespace"] == "myns"


def test_postprocess_components_invfilter_disabled(tmp_path, capsys):
    f = _make_ns_filter("myns", enabled=False)
    testf, config, inventory, components = _setup(tmp_path, f, invfilter=True)
    postprocess_components(config, inventory, components)
    assert testf.exists()
    with open(testf) as objf:
        obj = yaml.safe_load(objf)
        assert obj["metadata"]["namespace"] == "untouched"
    captured = capsys.readouterr()
    assert "Skipping disabled filter" in captured.out


def test_postprocess_components_aliased_component(tmp_path, capsys):
    f = _make_ns_filter("myns")
    testf, config, inventory, components = _setup(tmp_path, f, alias="component-alias")

    postprocess_components(config, inventory, components)

    assert testf.exists()
    with open(testf) as objf:
        obj = yaml.safe_load(objf)
        assert obj["metadata"]["namespace"] == "myns"


def test_postprocess_components_aliased_component_invfilter(tmp_path, capsys):
    f = _make_ns_filter("myns")
    testf, config, inventory, components = _setup(
        tmp_path, f, invfilter=True, alias="component-alias"
    )

    postprocess_components(config, inventory, components)

    assert testf.exists()
    with open(testf) as objf:
        obj = yaml.safe_load(objf)
        assert obj["metadata"]["namespace"] == "myns"


def test_postprocess_components_aliased_component_invfilter_custom_output(
    tmp_path, capsys
):
    f = _make_ns_filter("myns")
    f["filters"][0]["output_dir"] = "component-alias"
    testf, config, inventory, components = _setup(
        tmp_path, f, invfilter=True, alias="component-alias", aliased_output=True
    )

    postprocess_components(config, inventory, components)

    assert testf.exists()
    with open(testf) as objf:
        obj = yaml.safe_load(objf)
        assert obj["metadata"]["namespace"] == "myns"
