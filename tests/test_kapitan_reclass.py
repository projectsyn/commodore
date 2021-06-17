from pathlib import Path as P

from commodore.helpers import kapitan_inventory


class MockInventory:
    def __init__(self, invdir: P):
        self.invdir = invdir

    @property
    def inventory_dir(self):
        return self.invdir


class MockConfig:
    def __init__(self, invdir: P):
        self.inv = MockInventory(P(__file__).parent.absolute() / "testdata" / invdir)

    @property
    def inventory(self):
        return self.inv


def test_yml_yaml(tmp_path: P):
    config = MockConfig(invdir="inventory_yml_yaml")

    inv = kapitan_inventory(config)

    assert "test" in inv
    inv = inv["test"]
    assert "parameters" in inv
    assert "test" in inv["parameters"]
    assert "key1" in inv["parameters"]["test"]
    assert "value1" == inv["parameters"]["test"]["key1"]
    assert "key2" in inv["parameters"]["test"]
    assert "value2" == inv["parameters"]["test"]["key2"]


def test_applications(tmp_path: P):
    config = MockConfig("inventory_apps")

    apps = kapitan_inventory(config, key="applications")

    apps = apps.keys()
    assert "app1" in apps
    assert "app2" not in apps


def test_relative_refs(tmp_path: P):
    config = MockConfig("inventory_relative_refs")

    inv = kapitan_inventory(config)

    assert "test" in inv
    inv = inv["test"]
    assert "parameters" in inv
    assert "test" in inv["parameters"]
    assert "key1" in inv["parameters"]["test"]
    assert "value1" == inv["parameters"]["test"]["key1"]
