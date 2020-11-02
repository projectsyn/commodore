"""
Tests for component compile command
"""
import yaml
import pytest

from pathlib import Path as P
from subprocess import call
from textwrap import dedent


from click import ClickException
from git import Repo

from commodore.config import Config
from commodore.component.compile import compile_component
from test_component_template import test_run_component_new_command


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
    component_class = (
        tmp_path / "dependencies" / component_name / "class" / f"{component_name}.yml"
    )
    with open(component_class, "r") as file:
        file_contents = yaml.safe_load(file)

    filters = [
        {
            "path": component_name,
            "type": "builtin",
            "filter": "helm_namespace",
            "filterargs": {
                "namespace": "test-component-ns",
            },
        }
    ]
    file_contents["parameters"]["commodore"] = {
        "postprocess": {
            "filters": filters,
        }
    }
    with open(component_class, "w") as file:
        yaml.dump(file_contents, file)


def _cli_command_string(p: P, component: str) -> str:
    return f"commodore -d '{p}' component compile -o '{p}/testdir' '{p}/dependencies/{component}'"


def test_run_component_compile_command(tmp_path: P):
    """
    Run the component compile command
    """
    component_name = "test-component"
    _prepare_component(tmp_path, component_name)

    component_repo = Repo(tmp_path / "dependencies" / component_name)
    orig_remote_urls = list(component_repo.remote().urls)

    exit_status = call(
        _cli_command_string(tmp_path, component_name),
        shell=True,
    )
    assert exit_status == 0
    assert (
        tmp_path
        / "testdir"
        / "compiled"
        / component_name
        / "apps"
        / f"{component_name}.yaml"
    ).exists()
    rendered_yaml = (
        tmp_path
        / "testdir"
        / "compiled"
        / component_name
        / component_name
        / "test_service_account.yaml"
    )
    assert rendered_yaml.exists()
    with open(rendered_yaml) as file:
        target = yaml.safe_load(file)
        assert target["kind"] == "ServiceAccount"
        assert target["metadata"]["namespace"] == f"syn-{component_name}"

    assert list(component_repo.remote().urls) == orig_remote_urls


def test_run_component_compile_command_postprocess(tmp_path):
    """
    Run the component compile command for a component with a postprocessing
    filter
    """
    component_name = "test-component"
    _prepare_component(tmp_path, component_name)
    _add_postprocessing_filter(tmp_path, component_name)

    exit_status = call(
        _cli_command_string(tmp_path, component_name),
        shell=True,
    )
    assert exit_status == 0
    assert (
        tmp_path
        / "testdir"
        / "compiled"
        / component_name
        / "apps"
        / f"{component_name}.yaml"
    ).exists()
    rendered_yaml = (
        tmp_path
        / "testdir"
        / "compiled"
        / component_name
        / component_name
        / "test_service_account.yaml"
    )
    assert rendered_yaml.exists()
    with open(rendered_yaml) as file:
        target = yaml.safe_load(file)
        assert target["kind"] == "ServiceAccount"
        assert target["metadata"]["namespace"] == "test-component-ns"


def test_no_component_compile_command(tmp_path):
    with pytest.raises(ClickException) as excinfo:
        compile_component(Config(tmp_path), tmp_path / "foo", [], [], "./")
    assert "Could not find component class file" in str(excinfo)
