"""
Tests for component new command
"""
import os
import pytest
import yaml
from pathlib import Path as P
from subprocess import call


def setup_directory(tmp_path: P):
    os.chdir(tmp_path)

    os.makedirs(P('inventory', 'classes', 'components'), exist_ok=True)
    os.makedirs(P('inventory', 'classes', 'defaults'), exist_ok=True)
    os.makedirs(P('dependencies', 'lib'), exist_ok=True)
    os.makedirs(P('inventory', 'targets'), exist_ok=True)
    targetyml = P('inventory', 'targets', 'cluster.yml')
    with open(targetyml, 'w') as file:
        file.write('''classes:
        - test''')

    return targetyml


def test_run_component_new_command(tmp_path: P):
    """
    Run the component new command
    """

    targetyml = setup_directory(tmp_path)

    component_name = 'test-component'
    exit_status = call(f"commodore -vvv component new {component_name} --lib --pp", shell=True)
    assert exit_status == 0
    for file in [P('README.md'),
                 P('class', f"{component_name}.yml"),
                 P('component', 'main.jsonnet'),
                 P('component', 'app.jsonnet'),
                 P('lib', f"{component_name}.libsonnet"),
                 P('postprocess', 'filters.yml'),
                 P('docs', 'modules', 'ROOT', 'pages', 'references', 'parameters.adoc'),
                 P('docs', 'modules', 'ROOT', 'pages', 'index.adoc'),
                 ]:
        assert os.path.exists(P('dependencies', component_name, file))
    for file in [P('inventory', 'classes', 'components', f"{component_name}.yml"),
                 P('inventory', 'classes', 'defaults', f"{component_name}.yml"),
                 P('dependencies', 'lib', f"{component_name}.libsonnet")]:
        assert file.is_symlink()
    with open(targetyml) as file:
        target = yaml.safe_load(file)
        assert target['classes'][0] == f"defaults.{component_name}"
        assert target['classes'][-1] == f"components.{component_name}"


def test_run_component_new_command_with_name(tmp_path: P):
    """
    Run the component new command with the slug option set
    """

    setup_directory(tmp_path)

    component_name = 'Component with custom name'
    component_slug = 'named-component'
    readme_path = P('dependencies', component_slug, 'README.md')

    exit_status = call(f"commodore -vvv component new --name '{component_name}' {component_slug}", shell=True)

    assert exit_status == 0
    assert os.path.exists(readme_path)

    with open(readme_path, 'r') as file:
        data = file.read()
        assert component_name in data
        assert component_slug not in data


@pytest.mark.parametrize(
    "test_input",
    [
        'component-test-illegal',
        'test-illegal-',
        '-test-illegal',
        '00-test-illegal',
        'TestIllegal',
        'test_illegal',
    ]
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
    targetyml = setup_directory(tmp_path)

    component_name = 'test-component'
    exit_status = call(f"commodore -vvv component new {component_name} --lib --pp", shell=True)
    assert exit_status == 0

    exit_status = call(f"commodore -vvv component delete --force {component_name}", shell=True)
    assert exit_status == 0

    # Ensure the dependencies folder is gone.
    assert not P('dependencies', component_name).exists()

    # Links in the inventory should be gone too.
    for f in [P('inventory', 'classes', 'components', f"{component_name}.yml"),
              P('inventory', 'classes', 'defaults', f"{component_name}.yml"),
              P('dependencies', 'lib', f"{component_name}.libsonnet")]:
        assert not f.exists()

    with open(targetyml) as file:
        target = yaml.safe_load(file)
        classes = target['classes']
        assert f"defaults.{component_name}" not in classes
        assert f"components.{component_name}" not in classes


def test_deleting_inexistant_component(tmp_path: P):
    """
    Trying to delete a component that does not exist results in a non-0 exit
    code.
    """
    setup_directory(tmp_path)
    component_name = 'i-dont-exist'

    exit_status = call(f"commodore -vvv component delete --force {component_name}", shell=True)
    assert exit_status == 2
