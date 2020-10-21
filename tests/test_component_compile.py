"""
Tests for component compile command
"""
import os
import yaml
import pytest

from subprocess import call
from textwrap import dedent

from click import ClickException
from commodore.config import Config
from commodore.component.compile import compile_component
from test_component import test_run_component_new_command


def _prepare_component(tmp_path, component_name="test-component"):
    test_run_component_new_command(tmp_path=tmp_path)

    with open(
        tmp_path / "dependencies" / component_name / "component/main.jsonnet", "a"
    ) as file:
        file.write(
            dedent(
                """
            {
              "test_service_account": kube.ServiceAccount('test') {
                metadata+: {
                  namespace: params.namespace,
                },
              },
            }"""
            )
        )


def _add_postprocessing_filter(tmp_path, component_name="test-component"):
    with open(
        tmp_path / "dependencies" / component_name / "postprocess" / "filters.yml", "w"
    ) as file:
        filters = {
            "filters": [
                {
                    "path": component_name,
                    "type": "builtin",
                    "filter": "helm_namespace",
                    "filterargs": {
                        "namespace": "test-component-ns",
                    },
                }
            ]
        }
        yaml.dump(filters, file)


def test_run_component_compile_command(tmp_path):
    """
    Run the component compile command
    """

    os.chdir(tmp_path)

    component_name = "test-component"
    _prepare_component(tmp_path, component_name)

    exit_status = call(
        f"commodore component compile -o ./testdir dependencies/{component_name}",
        shell=True,
    )
    assert exit_status == 0
    assert os.path.exists(
        tmp_path
        / "testdir/standalone/compiled"
        / component_name
        / f"apps/{component_name}.yaml"
    )
    rendered_yaml = (
        tmp_path
        / "testdir/standalone/compiled"
        / component_name
        / component_name
        / "test_service_account.yaml"
    )
    assert rendered_yaml.exists()
    with open(rendered_yaml) as file:
        target = yaml.safe_load(file)
        assert target["kind"] == "ServiceAccount"
        assert target["metadata"]["namespace"] == f"syn-{component_name}"


def test_run_component_compile_command_postprocess(tmp_path):
    """
    Run the component compile command for a component with a postprocessing
    filter
    """

    os.chdir(tmp_path)

    component_name = "test-component"
    _prepare_component(tmp_path, component_name)
    _add_postprocessing_filter(tmp_path, component_name)

    exit_status = call(
        f"commodore component compile -o ./testdir dependencies/{component_name}",
        shell=True,
    )
    assert exit_status == 0
    assert os.path.exists(
        tmp_path
        / "testdir/standalone/compiled"
        / component_name
        / f"apps/{component_name}.yaml"
    )
    rendered_yaml = (
        tmp_path
        / "testdir/standalone/compiled"
        / component_name
        / component_name
        / "test_service_account.yaml"
    )
    assert rendered_yaml.exists()
    with open(rendered_yaml) as file:
        target = yaml.safe_load(file)
        assert target["kind"] == "ServiceAccount"
        assert target["metadata"]["namespace"] == "test-component-ns"


def test_no_component_compile_command():
    with pytest.raises(ClickException) as excinfo:
        compile_component(Config(), "./", [], [], "./")
    assert "Could not find component class file" in str(excinfo)
