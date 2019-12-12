"""
Tests for new-component command
"""
import os
from pathlib import Path as P


def test_run_newcomponent_command():
    """
    Run the new-component command
    """

    os.makedirs(P('inventory', 'classes', 'components'))
    os.makedirs(P('dependencies', 'lib'))
    os.makedirs(P('inventory', 'targets'))
    with open(P('inventory', 'targets', 'cluster.yml'), 'w') as file:
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
