import os

from pathlib import Path

import git

from commodore.cluster import update_target
from commodore.component import Component
from commodore.config import Config
from commodore.dependency_mgmt import create_component_symlinks
from commodore.helpers import kapitan_inventory, yaml_dump, yaml_load

from conftest import MockMultiDependency


def _setup(tmp_path: Path):
    cfg = Config(
        work_dir=tmp_path,
        api_url="https://syn.example.com",
        api_token="abcd1234",
    )

    os.makedirs(cfg.inventory.defaults_dir)
    os.makedirs(cfg.inventory.components_dir)
    os.makedirs(cfg.inventory.global_config_dir)
    os.makedirs(cfg.inventory.params_dir)

    os.makedirs(tmp_path / "dependencies" / "test")
    cdep = MockMultiDependency(git.Repo.init(tmp_path / "repo.git"))
    c = Component("test", cdep, work_dir=tmp_path)
    os.makedirs(c.class_file.parent)

    yaml_dump(
        {
            "parameters": {
                "kapitan": {
                    "compile": [
                        {
                            "input_paths": ["input/path/file.txt"],
                            "input_type": "copy",
                            "output_path": "test",
                        }
                    ]
                }
            }
        },
        c.class_file,
    )
    yaml_dump(
        {
            "parameters": {
                "test": {
                    "multi_instance": True,
                    "namespace": "syn-test",
                    "instance_value": "${_instance}",
                }
            }
        },
        c.defaults_file,
    )
    yaml_dump(
        {
            "parameters": {
                "cluster": {
                    "name": "c-cluster-id-1234",
                    "tenant": "t-tenant-id-1234",
                },
            },
        },
        cfg.inventory.params_file,
    )
    yaml_dump({"classes": []}, cfg.inventory.global_config_dir / "commodore.yml")

    cfg.register_component(c)
    create_component_symlinks(cfg, c)
    cfg.register_component_aliases({"test-1": "test"})

    for alias, component in cfg.get_component_aliases().items():
        update_target(cfg, alias, component=component)

    return cfg


def test_render_inventory_instantiated_component_no_custom_config(tmp_path: Path):
    cfg = _setup(tmp_path)

    inv = kapitan_inventory(cfg)

    assert inv["test-1"]["parameters"]["test"]["instance_value"] == "test-1"

    pass


def test_render_inventory_instantiated_component_custom_config(tmp_path: Path):
    cfg = _setup(tmp_path)
    # Add parameter in test_1
    params = yaml_load(cfg.inventory.params_file)
    params["parameters"]["test_1"] = {"instance_value": "testing"}
    yaml_dump(params, cfg.inventory.params_file)

    inv = kapitan_inventory(cfg)

    assert inv["test-1"]["parameters"]["test"]["instance_value"] == "testing"
