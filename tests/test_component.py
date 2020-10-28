"""
Tests for component new command
"""
import json
import os
import pytest
import yaml
from pathlib import Path as P
from subprocess import call
from git import Repo

from commodore.component import Component, component_dir


def setup_directory(tmp_path: P):
    os.chdir(tmp_path)

    os.makedirs(P("inventory", "classes", "components"), exist_ok=True)
    os.makedirs(P("inventory", "classes", "defaults"), exist_ok=True)
    os.makedirs(P("dependencies", "lib"), exist_ok=True)
    os.makedirs(P("inventory", "targets"), exist_ok=True)
    jsonnetfile = P("jsonnetfile.json")
    with open(jsonnetfile, "w") as jf:
        json.dump({"version": 1, "dependencies": [], "legacyImports": True}, jf)


def test_run_component_new_command(tmp_path: P):
    """
    Run the component new command
    """

    setup_directory(tmp_path)

    component_name = "test-component"
    exit_status = call(
        f"commodore -vvv component new {component_name} --lib --pp", shell=True
    )
    assert exit_status == 0
    for file in [
        P("README.md"),
        P("class", f"{component_name}.yml"),
        P("component", "main.jsonnet"),
        P("component", "app.jsonnet"),
        P("lib", f"{component_name}.libsonnet"),
        P("postprocess", "filters.yml"),
        P("docs", "modules", "ROOT", "pages", "references", "parameters.adoc"),
        P("docs", "modules", "ROOT", "pages", "index.adoc"),
    ]:
        assert P("dependencies", component_name, file).exists()
    for file in [
        P("inventory", "classes", "components", f"{component_name}.yml"),
        P("inventory", "classes", "defaults", f"{component_name}.yml"),
        P("dependencies", "lib", f"{component_name}.libsonnet"),
        P("vendor", component_name),
    ]:
        assert file.is_symlink()
    targetyml = P("inventory", "targets", f"{component_name}.yml")
    assert targetyml.exists()
    with open(targetyml) as file:
        target = yaml.safe_load(file)
        assert f"defaults.{component_name}" in target["classes"]
        assert target["classes"][-1] == f"components.{component_name}"
        assert target["parameters"]["kapitan"]["vars"]["target"] == component_name
    # Check that there are no uncommited files in the component repo
    repo = Repo(P("dependencies", component_name))
    assert not repo.is_dirty()
    assert not repo.untracked_files


def test_run_component_new_command_with_name(tmp_path: P):
    """
    Run the component new command with the slug option set
    """

    setup_directory(tmp_path)

    component_name = "Component with custom name"
    component_slug = "named-component"
    readme_path = P("dependencies", component_slug, "README.md")

    exit_status = call(
        f"commodore -vvv component new --name '{component_name}' {component_slug}",
        shell=True,
    )

    assert exit_status == 0
    assert os.path.exists(readme_path)

    with open(readme_path, "r") as file:
        data = file.read()
        assert component_name in data
        assert component_slug not in data


@pytest.mark.parametrize(
    "test_input",
    [
        "component-test-illegal",
        "test-illegal-",
        "-test-illegal",
        "00-test-illegal",
        "TestIllegal",
        "test_illegal",
    ],
)
def test_run_component_new_command_with_illegal_slug(tmp_path: P, test_input):
    """
    Run the component new command with an illegal slug
    """
    setup_directory(tmp_path)
    exit_status = call(f"commodore -vvv component new {test_input}", shell=True)
    assert exit_status != 0


def test_run_component_new_then_delete(tmp_path: P):
    """
    Create a new component, then immediately delete it.
    """
    setup_directory(tmp_path)

    component_name = "test-component"
    exit_status = call(
        f"commodore -vvv component new {component_name} --lib --pp", shell=True
    )
    assert exit_status == 0

    exit_status = call(
        f"commodore -vvv component delete --force {component_name}", shell=True
    )
    assert exit_status == 0

    # Ensure the dependencies folder is gone.
    assert not P("dependencies", component_name).exists()

    # Links in the inventory should be gone too.
    for f in [
        P("inventory", "classes", "components", f"{component_name}.yml"),
        P("inventory", "classes", "defaults", f"{component_name}.yml"),
        P("dependencies", "lib", f"{component_name}.libsonnet"),
        P("vendor", component_name),
    ]:
        assert not f.exists()

    targetyml = P("inventory", "targets", f"{component_name}.yml")
    assert not targetyml.exists()


def test_deleting_inexistant_component(tmp_path: P):
    """
    Trying to delete a component that does not exist results in a non-0 exit
    code.
    """
    setup_directory(tmp_path)
    component_name = "i-dont-exist"

    exit_status = call(
        f"commodore -vvv component delete --force {component_name}", shell=True
    )
    assert exit_status == 2


def _init_repo(tmp_path: P, cn: str, url: str):
    setup_directory(tmp_path)
    cr = Repo.init(component_dir(cn))
    cr.create_remote("origin", url)


def test_init_existing_component(tmp_path: P):
    cn = "test-component"
    orig_url = "git@github.com:projectsyn/commodore.git"
    _init_repo(tmp_path, cn, orig_url)

    c = Component(cn)

    for url in c.repo.remote().urls:
        assert url == orig_url
