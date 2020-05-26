"""
Tests for new-component command
"""
import os
import yaml
from pathlib import Path as P


def test_run_newcomponent_command():
    """
    Run the new-component command
    """

    os.makedirs(P('inventory', 'classes', 'components'), exist_ok=True)
    os.makedirs(P('inventory', 'classes', 'defaults'), exist_ok=True)
    os.makedirs(P('dependencies', 'lib'), exist_ok=True)
    os.makedirs(P('inventory', 'targets'), exist_ok=True)
    targetyml = P('inventory', 'targets', 'cluster.yml')
    with open(targetyml, 'w') as file:
        file.write('''classes:
        - test''')
    component_name = 'test-component'
    exit_status = os.system(f"commodore -vvv new-component {component_name} --lib --pp")
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
