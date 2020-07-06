"""
Tests for component new command
"""
import os
import yaml
from pathlib import Path as P


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
    exit_status = os.system(f"commodore -vvv component new {component_name} --lib --pp")
    assert exit_status == 0
    for file in [P('README.md'),
                 P('class', f"{component_name}.yml"),
                 P('component', 'main.jsonnet'),
                 P('component', 'app.jsonnet'),
                 P('lib', f"{component_name}.libjsonnet"),
                 P('postprocess', 'filters.yml'), ]:
        assert os.path.exists(P('dependencies', component_name, file))
    for file in [P('inventory', 'classes', 'components',
                   f"{component_name}.yml"),
                 P('inventory', 'classes', 'defaults',
                   f"{component_name}.yml"),
                 P('dependencies', 'lib', f"{component_name}.libjsonnet")]:
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

    exit_status = os.system(f"commodore -vvv component new --name '{component_name}' {component_slug}")

    assert exit_status == 0
    assert os.path.exists(readme_path)

    with open(readme_path, 'r') as file:
        data = file.read()
        assert component_name in data
        assert component_slug not in data
