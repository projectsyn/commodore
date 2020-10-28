from pathlib import Path as P

from commodore.component import Component
from commodore.inventory import Inventory


def test_inventory_dir():
    assert str(Inventory().inventory_dir) == "inventory"
    assert str(Inventory(work_dir=P("./foo")).inventory_dir) == "foo/inventory"


def test_dependencies_dir():
    assert str(Inventory().dependencies_dir) == "dependencies"
    assert str(Inventory(work_dir=P("./bar")).dependencies_dir) == "bar/dependencies"


def test_classes_dir():
    assert str(Inventory().classes_dir) == "inventory/classes"
    assert str(Inventory(work_dir=P("./baz")).classes_dir) == "baz/inventory/classes"


def test_components_dir():
    assert str(Inventory().components_dir) == "inventory/classes/components"
    assert (
        str(Inventory(work_dir=P("./foo")).components_dir)
        == "foo/inventory/classes/components"
    )


def test_defaults_dir():
    assert str(Inventory().defaults_dir) == "inventory/classes/defaults"
    assert (
        str(Inventory(work_dir=P("./bar")).defaults_dir)
        == "bar/inventory/classes/defaults"
    )


def test_targets_dir():
    assert str(Inventory().targets_dir) == "inventory/targets"
    assert str(Inventory(work_dir=P("./baz")).targets_dir) == "baz/inventory/targets"


def test_lib_dir():
    assert str(Inventory().lib_dir) == "dependencies/lib"
    assert str(Inventory(work_dir=P("./foo")).lib_dir) == "foo/dependencies/lib"


def test_libs_dir():
    assert str(Inventory().libs_dir) == "dependencies/libs"
    assert str(Inventory(work_dir=P("./bar")).libs_dir) == "bar/dependencies/libs"


def test_global_config_dir():
    assert str(Inventory().global_config_dir) == "inventory/classes/global"
    assert (
        str(Inventory(work_dir=P("./baz")).global_config_dir)
        == "baz/inventory/classes/global"
    )


def test_tenant_config_dir():
    assert str(Inventory().tenant_config_dir("t-foo")) == "inventory/classes/t-foo"
    assert (
        str(Inventory(work_dir=P("./baz")).tenant_config_dir("t-bar"))
        == "baz/inventory/classes/t-bar"
    )


def test_component_file(tmp_path: P):
    assert (
        str(Inventory().component_file("foo")) == "inventory/classes/components/foo.yml"
    )
    assert (
        str(Inventory().component_file(Component("baz")))
        == "inventory/classes/components/baz.yml"
    )
    assert (
        str(Inventory(work_dir=P("./baz")).component_file("bar"))
        == "baz/inventory/classes/components/bar.yml"
    )


def test_defaults_file(tmp_path: P):
    assert str(Inventory().defaults_file("foo")) == "inventory/classes/defaults/foo.yml"
    assert (
        str(Inventory().defaults_file(Component("baz")))
        == "inventory/classes/defaults/baz.yml"
    )
    assert (
        str(Inventory(work_dir=P("./baz")).defaults_file("bar"))
        == "baz/inventory/classes/defaults/bar.yml"
    )


def test_target_file(tmp_path: P):
    assert str(Inventory().target_file("foo")) == "inventory/targets/foo.yml"
    assert str(Inventory().target_file(Component("baz"))) == "inventory/targets/baz.yml"
    assert (
        str(Inventory(work_dir=P("./baz")).target_file("bar"))
        == "baz/inventory/targets/bar.yml"
    )


def ensure_dirs(tmp_path: P):
    dirs = [
        tmp_path / "inventory/classes/components",
        tmp_path / "inventory/classes/defaults",
        tmp_path / "dependencies/lib",
        tmp_path / "dependencies/libs",
        tmp_path / "inventory/targets",
    ]
    for d in dirs:
        assert not d.is_dir()

    Inventory(work_dir=tmp_path).ensure_dirs()

    for d in dirs:
        assert d.is_dir()
