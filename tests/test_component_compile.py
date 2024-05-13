"""
Tests for component compile command
"""

import shutil
import os

from pathlib import Path as P
from subprocess import call, run
from textwrap import dedent
from typing import Optional

import yaml
import pytest

from click import ClickException
from git import Repo

from commodore.config import Config
from commodore.component import component_parameters_key
from commodore.component.compile import compile_component

from conftest import RunnerFunc
from test_component_template import call_component_new


def _prepare_component(
    tmp_path: P,
    cli_runner: RunnerFunc,
    component_name: str = "test-component",
    subpath: str = "",
) -> P:
    if not subpath:
        call_component_new(tmp_path, cli_runner, lib="--lib")
        component_root = tmp_path / "dependencies" / component_name
    else:
        call_component_new(tmp_path / "tmp", cli_runner, lib="--lib")
        component_root = tmp_path / component_name / subpath
        shutil.copytree(
            tmp_path / "tmp" / "dependencies" / "test-component", component_root
        )
        shutil.move(str(component_root / ".git"), str(tmp_path / component_name))

    with open(component_root / "component/main.jsonnet", "a") as file:
        file.write(
            dedent(
                """
            {
              "test_service_account": kube.ServiceAccount('test') {
                metadata+: {
                  namespace: params.namespace,
                  annotations: {
                    foo: std.get(params, "foo", "default"),
                  },
                  labels+: {
                    cluster_id: inv.parameters.cluster.name,
                    cluster_name: inv.parameters.cluster.display_name,
                    tenant_id: inv.parameters.cluster.tenant,
                    tenant_name: inv.parameters.cluster.tenant_display_name,
                  },
                },
              },
            }"""
            )
        )
    return component_root


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


def _make_instance_aware(tmp_path, component_name="test-component"):
    component_defaults = (
        tmp_path / "dependencies" / component_name / "class" / "defaults.yml"
    )
    with open(component_defaults, "r") as file:
        file_contents = yaml.safe_load(file)

    file_contents["parameters"][component_parameters_key(component_name)]["=_metadata"][
        "multi_instance"
    ] = True

    with open(component_defaults, "w") as file:
        yaml.dump(file_contents, file)


def _cli_command_string(
    p: P, component: str, instance: Optional[str] = None, subpath: Optional[str] = None
) -> str:
    if subpath:
        cpath = f"'{p}/{component}/{subpath}' -n {component}"
    else:
        cpath = f"'{p}/dependencies/{component}'"
    cmd = f"commodore -d '{p}' component compile -o '{p}/testdir' {cpath}"
    if instance is not None:
        cmd = f"{cmd} -a {instance}"
    return cmd


def test_run_component_compile_command(tmp_path: P, cli_runner: RunnerFunc):
    """
    Run the component compile command
    """
    component_name = "test-component"
    _prepare_component(tmp_path, cli_runner, component_name)

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
        # Verify that cluster metadata is provided correctly to `component compile`
        assert target["metadata"]["labels"]["cluster_id"] == "c-green-test-1234"
        assert target["metadata"]["labels"]["cluster_name"] == "Test Cluster 1234"
        assert target["metadata"]["labels"]["tenant_id"] == "t-silent-test-1234"
        assert target["metadata"]["labels"]["tenant_name"] == "Test Tenant 1234"

    assert list(component_repo.remote().urls) == orig_remote_urls


def test_run_component_compile_command_postprocess(tmp_path: P, cli_runner: RunnerFunc):
    """
    Run the component compile command for a component with a postprocessing
    filter
    """
    component_name = "test-component"
    _prepare_component(tmp_path, cli_runner, component_name)
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


@pytest.mark.parametrize("instance_aware", [True, False])
def test_run_component_compile_command_instance(
    tmp_path: P, capsys, cli_runner: RunnerFunc, instance_aware: bool
):
    """
    Run the component compile command for a component with a postprocessing
    filter
    """
    component_name = "test-component"
    instance_name = "test-instance"
    _prepare_component(tmp_path, cli_runner, component_name)
    values_file = tmp_path / "values.yml"
    values = {"parameters": {component_parameters_key(component_name): {"foo": "foo"}}}
    if instance_aware:
        _make_instance_aware(tmp_path, component_name)
        values["parameters"][component_parameters_key(instance_name)] = {"foo": "bar"}

    with open(values_file, "w", encoding="utf-8") as vf:
        yaml.safe_dump(values, vf)

    result = run(
        _cli_command_string(tmp_path, component_name, instance_name)
        + f" -f {values_file}",
        shell=True,
        capture_output=True,
    )

    exit_status = result.returncode

    if not instance_aware:
        assert exit_status == 1
        assert (
            f"Error: Component {component_name} with alias {instance_name} does not support instantiation.\n"
            in result.stderr.decode("utf-8")
        )
    else:
        assert exit_status == 0
        assert (
            tmp_path
            / "testdir"
            / "compiled"
            / instance_name
            / "apps"
            / f"{component_name}.yaml"
        ).exists()
        rendered_yaml = (
            tmp_path
            / "testdir"
            / "compiled"
            / instance_name
            / component_name
            / "test_service_account.yaml"
        )
        assert rendered_yaml.exists()
        with open(rendered_yaml) as file:
            target = yaml.safe_load(file)
            assert target["kind"] == "ServiceAccount"
            assert target["metadata"]["namespace"] == f"syn-{component_name}"
            assert target["metadata"]["annotations"]["foo"] == "bar"


def test_component_compile_subpath(tmp_path: P, cli_runner: RunnerFunc):
    component_name = "test-component"
    _prepare_component(tmp_path, cli_runner, component_name, subpath="component")

    exit_status = call(
        _cli_command_string(tmp_path, component_name, subpath="component"),
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
        assert target["metadata"]["namespace"] == "syn-test-component"


def test_no_component_compile_command(tmp_path: P):
    with pytest.raises(ClickException) as excinfo:
        compile_component(Config(tmp_path), tmp_path / "foo", None, [], [], "./", "")
    assert (
        f"Can't compile component, repository {tmp_path / 'foo'} doesn't exist"
        in str(excinfo)
    )


def test_component_compile_no_repo(tmp_path: P, cli_runner: RunnerFunc):
    component_name = "test-component"
    cpath = _prepare_component(tmp_path, cli_runner, component_name)
    os.unlink(cpath / ".git")

    exit_status = call(_cli_command_string(tmp_path, component_name), shell=True)

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
        assert target["metadata"]["namespace"] == "syn-test-component"


def test_component_compile_kustomize(tmp_path: P, cli_runner: RunnerFunc):
    component_name = "test-component"
    component_path = _prepare_component(tmp_path, cli_runner, component_name)

    with open(
        component_path / "component" / "kustomization.jsonnet", "w", encoding="utf-8"
    ) as f:
        f.write(
            """
local com = import 'lib/commodore.libjsonnet';

com.Kustomization(
  'https://github.com/appuio/appuio-cloud-agent//config/default',
  'v0.5.0',
  {
    'ghcr.io/appuio/appuio-cloud-agent': {
      newTag: 'v0.5.0',
      newName: 'ghcr.io/appuio/appuio-cloud-agent',
    },
  },
  {
    namespace: 'foo',
  }
)"""
        )
    with open(
        component_path / "class" / f"{component_name}.yml", "r", encoding="utf-8"
    ) as cyaml:
        component_yaml = yaml.safe_load(cyaml)

    component_yaml["parameters"]["kapitan"]["compile"].extend(
        [
            {
                "input_type": "jsonnet",
                "input_paths": ["${_base_directory}/component/kustomization.jsonnet"],
                "output_path": "${_base_directory}/kust/",
            },
            {
                "input_type": "external",
                "input_paths": ["${_kustomize_wrapper}"],
                "output_path": ".",
                "env_vars": {
                    "INPUT_DIR": "${_base_directory}/kust",
                },
                "args": [
                    "\\${compiled_target_dir}/${_instance}/",
                ],
            },
        ]
    )

    with open(
        component_path / "class" / f"{component_name}.yml", "w", encoding="utf-8"
    ) as cyaml:
        yaml.safe_dump(component_yaml, cyaml)

    exit_status = call(
        _cli_command_string(tmp_path, component_name),
        shell=True,
    )

    assert exit_status == 0

    kustomization = component_path / "kust" / "kustomization.yaml"
    assert kustomization.is_file()
    with open(kustomization, "r", encoding="utf-8") as f:
        kustomization_yaml = yaml.safe_load(f)
        assert set(kustomization_yaml.keys()) == {"images", "namespace", "resources"}
        assert kustomization_yaml["namespace"] == "foo"
        assert len(kustomization_yaml["resources"]) == 1
        assert (
            kustomization_yaml["resources"][0]
            == "https://github.com/appuio/appuio-cloud-agent//config/default?ref=v0.5.0"
        )
        assert len(kustomization_yaml["images"]) == 1
        assert kustomization_yaml["images"][0] == {
            "name": "ghcr.io/appuio/appuio-cloud-agent",
            "newName": "ghcr.io/appuio/appuio-cloud-agent",
            "newTag": "v0.5.0",
        }

    rendered_manifests = (
        tmp_path / "testdir" / "compiled" / component_name / component_name
    )
    assert rendered_manifests.is_dir()
    with open(
        rendered_manifests / "apps_v1_deployment_appuio-cloud-agent.yaml",
        "r",
        encoding="utf-8",
    ) as f:
        deploy = yaml.safe_load(f)
        assert deploy["kind"] == "Deployment"
        assert deploy["metadata"]["namespace"] == "foo"
        container = deploy["spec"]["template"]["spec"]["containers"][0]
        assert container["image"] == "ghcr.io/appuio/appuio-cloud-agent:v0.5.0"
