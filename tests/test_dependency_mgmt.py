"""
Unit-tests for dependency management
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from unittest.mock import patch
from pathlib import Path

import click
import git
import pytest
import yaml

from commodore import dependency_mgmt
from commodore.config import Config
from commodore.component import Component
from commodore.inventory import Inventory
from commodore.package import package_dependency_dir, Package


from commodore.dependency_mgmt.version_parsing import DependencySpec
from test_package import _setup_package_remote

from conftest import MockMultiDependency


def setup_components_upstream(
    tmp_path: Path, components: Iterable[str], aliases: dict[str, str] = {}
):
    # Prepare minimum component directories
    upstream = tmp_path / "upstream"
    component_specs = {}
    for component in components:
        component_specs[component] = _prepare_repository(upstream, component, component)

        for alias in aliases.keys():
            if aliases[alias] == component:
                component_specs[alias] = component_specs[component]

    return component_specs


def setup_aliases_upstream(
    tmp_path: Path, aliases: Iterable[tuple[str, str]], sub_path: str = ""
):
    upstream = tmp_path / "upstream"
    component_specs = {}
    for alias, component in aliases:
        component_specs[alias] = _prepare_repository(
            upstream, alias, component, sub_path
        )

    return component_specs


def _prepare_repository(
    upstream: Path, repo_name: str, component_name: str, sub_path: str = ""
):
    repo_path = upstream / repo_name
    url = f"file://{repo_path.resolve()}"
    version = None
    repo = git.Repo.init(repo_path)

    class_dir = repo_path / sub_path / "class"
    class_dir.mkdir(parents=True, exist_ok=True)
    (class_dir / "defaults.yml").touch(exist_ok=True)
    (class_dir / f"{component_name}.yml").touch(exist_ok=True)

    class_path = f"{sub_path}/class".strip("/")

    repo.index.add([f"{class_path}/defaults.yml", f"{class_path}/{component_name}.yml"])
    repo.index.commit("component defaults")
    return DependencySpec(url, version, sub_path)


def test_create_component_symlinks_fails(config: Config, tmp_path: Path, mockdep):
    component = Component("my-component", mockdep, work_dir=tmp_path)
    with pytest.raises(click.ClickException) as e:
        dependency_mgmt.create_component_symlinks(config, component)

    assert "Source does not exist" in str(e.value)


def setup_mock_component(tmp_path: Path, name="my-component") -> Component:
    cdep = MockMultiDependency(git.Repo.init(tmp_path / "repo.git"))
    component = Component(name, cdep, work_dir=tmp_path)
    component.class_file.parent.mkdir(parents=True, exist_ok=True)
    with open(component.class_file, "w") as f:
        f.writelines(["class"])
    with open(component.defaults_file, "w") as f:
        f.writelines(["default"])
    lib_dir = component.target_directory / "lib"
    lib_dir.mkdir(parents=True, exist_ok=True)
    lib_file = lib_dir / f"{component.name}.libjsonnet"
    with open(lib_file, "w") as f:
        f.writelines(["lib"])

    return component


def test_create_component_symlinks(capsys, config: Config, tmp_path):
    component = setup_mock_component(tmp_path)
    inv = Inventory(work_dir=tmp_path)
    inv.ensure_dirs()

    dependency_mgmt.create_component_symlinks(config, component)

    expected_symlinks = [
        (
            tmp_path / "inventory" / "classes" / "components" / f"{component.name}.yml",
            "class",
        ),
        (
            tmp_path / "inventory" / "classes" / "defaults" / f"{component.name}.yml",
            "default",
        ),
        (tmp_path / "dependencies" / "lib" / "my-component.libjsonnet", "lib"),
    ]

    for path, marker in expected_symlinks:
        # Ensure symlinks exist
        assert path.is_symlink()
        # Ensure symlink targets exist
        assert path.resolve().is_file()
        # Ensure symlinked file contains correct marker content
        with open(path) as f:
            fcontents = f.readlines()
            assert fcontents[0] == marker
    assert capsys.readouterr().out == ""


def _setup_mock_inventory(patch_inventory, aliases={}, packages=[], omit_version=False):
    components = {
        "test-component": {
            "url": "https://github.com/projectsyn/component-test-component.git",
            "version": "master",
        },
        "other-component": {
            "url": "ssh://git@git.acme.com/some/component.git",
            "version": "v1.0.0",
        },
        "third-component": {
            "url": "https://github.com/projectsyn/component-third-component.git",
            "version": "feat/test",
        },
    }
    if omit_version:
        del components["other-component"]["version"]

    assert set(aliases.keys()) <= set(components.keys())
    applications = list(components.keys())
    for c, a in aliases.items():
        applications.append(f"{c} as {a}")
    for p in packages:
        applications.append(f"pkg.{p}")
    params = {"components": components}
    nodes = {
        a: {"applications": sorted(applications), "parameters": params}
        for a in applications
    }
    nodes["cluster"] = {"applications": sorted(applications), "parameters": params}
    mock_inventory = {
        "applications": {a: applications for a in applications},
        "nodes": nodes,
    }

    def inv(inventory_dir, key="nodes", ignore_class_notfound=False):
        return mock_inventory[key]

    patch_inventory.side_effect = inv

    return mock_inventory["nodes"]["cluster"]["parameters"]["components"]


@patch("commodore.dependency_mgmt._read_components")
@patch("commodore.dependency_mgmt._discover_components")
def test_fetch_components(patch_discover, patch_read, config: Config, tmp_path: Path):
    components = ["component-one", "component-two"]
    patch_discover.return_value = (components, {})
    patch_read.return_value = setup_components_upstream(tmp_path, components)

    dependency_mgmt.fetch_components(config)

    for component in components:
        assert component in config._components
        assert (
            tmp_path / "inventory" / "classes" / "components" / f"{component}.yml"
        ).is_symlink()
        assert (
            tmp_path / "inventory" / "classes" / "defaults" / f"{component}.yml"
        ).is_symlink()
        assert (tmp_path / "dependencies" / component).is_dir()


@patch("commodore.dependency_mgmt._read_components")
@patch("commodore.dependency_mgmt._discover_components")
def test_fetch_components_with_alias_version(
    patch_discover, patch_read, config: Config, tmp_path: Path
):
    components = ["component-one", "component-two"]
    aliases = {
        "alias-one": "component-one",
        "alias-two": "component-two",
        "alias-three": "component-two",
    }
    patch_discover.return_value = (components, aliases)

    forked_aliases = [("alias-two", "component-two")]
    forked_aliases2 = [("alias-three", "component-two")]
    # setup one alias with different repo
    aspecs = setup_aliases_upstream(tmp_path, forked_aliases)
    # setup other alias with a subdirectory
    aspecs2 = setup_aliases_upstream(tmp_path, forked_aliases2, "subdirectory")

    rv = setup_components_upstream(tmp_path, components, aliases)
    rv["alias-two"] = aspecs["alias-two"]
    rv["alias-three"] = aspecs2["alias-three"]

    patch_read.return_value = rv

    dependency_mgmt.fetch_components(config)

    for component in components:
        assert component in config._components
        assert (
            tmp_path / "inventory" / "classes" / "components" / f"{component}.yml"
        ).is_symlink()
        assert (
            tmp_path / "inventory" / "classes" / "defaults" / f"{component}.yml"
        ).is_symlink()
        assert (tmp_path / "dependencies" / component).is_dir()

    for alias in aliases.keys():
        assert alias in config._component_aliases
        assert (
            tmp_path / "inventory" / "classes" / "components" / f"{alias}.yml"
        ).is_symlink()
        assert (
            tmp_path / "inventory" / "classes" / "defaults" / f"{alias}.yml"
        ).is_symlink()


@pytest.mark.parametrize("dirty_alias", [False, True])
@patch("commodore.dependency_mgmt._read_components")
@patch("commodore.dependency_mgmt._discover_components")
def test_fetch_components_raises(
    patch_discover, patch_read, config: Config, tmp_path: Path, dirty_alias: bool
):
    components = ["foo"]
    aliases = {"bar": "foo"}
    patch_discover.return_value = (components, aliases)
    patch_read.return_value = setup_components_upstream(tmp_path, components)
    patch_read.return_value["bar"] = patch_read.return_value["foo"]

    dependency_mgmt.fetch_components(config)

    c = config.get_components()["foo"]
    dirty_name = "bar" if dirty_alias else "foo"

    with open(
        c.alias_directory(dirty_name) / "class" / "defaults.yml",
        "w",
        encoding="utf-8",
    ) as f:
        f.write("foo: bar\n")

    config._dependency_repos.clear()
    config._components.clear()

    if dirty_alias:
        msg = "Component alias bar has uncommitted changes. Please specify `--force` to discard them"
    else:
        msg = "Component foo has uncommitted changes. Please specify `--force` to discard them"

    with pytest.raises(click.ClickException) as excinfo:
        dependency_mgmt.fetch_components(config)

    assert msg in str(excinfo.value)


@patch("commodore.dependency_mgmt._read_components")
@patch("commodore.dependency_mgmt._discover_components")
def test_fetch_components_raises_giterror(
    patch_discover, patch_read, config: Config, tmp_path: Path
):
    components = ["foo"]
    patch_discover.return_value = (components, {})
    read_retval = setup_components_upstream(tmp_path, components)
    read_retval["foo"].version = "nonexistent"
    patch_read.return_value = read_retval

    with pytest.raises(Exception) as excinfo:
        dependency_mgmt.fetch_components(config)

    assert "Failed to checkout revision 'nonexistent'" in str(excinfo.value)


@patch("commodore.dependency_mgmt._read_components")
@patch("commodore.dependency_mgmt._discover_components")
def test_fetch_components_is_minimal(
    patch_discover, patch_urls, config: Config, tmp_path: Path
):
    components = ["component-one", "component-two"]
    other_components = ["component-three", "component-four"]
    patch_discover.return_value = (components, {})
    patch_urls.return_value = setup_components_upstream(tmp_path, components)
    # Setup upstreams for components which are not included
    other_cspecs = setup_components_upstream(tmp_path, other_components)
    for cn, cspec in other_cspecs.items():
        patch_urls.return_value[cn] = cspec

    dependency_mgmt.fetch_components(config)
    print(config._components)

    for component in components:
        assert component in config._components
        assert (
            tmp_path / "inventory" / "classes" / "components" / f"{component}.yml"
        ).is_symlink()
        assert (
            tmp_path / "inventory" / "classes" / "defaults" / f"{component}.yml"
        ).is_symlink()
        assert (tmp_path / "dependencies" / component).is_dir()

    for component in other_components:
        assert component not in config._components
        assert not (tmp_path / "dependencies" / component).exists()


def _setup_register_components(tmp_path: Path, aliases: dict[str, str] = {}):
    inv = Inventory(tmp_path)
    inv.ensure_dirs()
    component_dirs = ["foo", "bar", "baz"]
    other_dirs = ["lib", "libs"]
    for directory in component_dirs + other_dirs:
        cpath = tmp_path / "dependencies" / directory
        os.makedirs(cpath, exist_ok=True)
        r = git.Repo.init(cpath)
        r.create_remote("origin", f"ssh://git@example.com/git/{directory}")
        os.makedirs(cpath / "class", exist_ok=True)
        with open(cpath / "class" / "defaults.yml", "w") as f:
            f.write("")
        with open(cpath / "class" / f"{directory}.yml", "w") as f:
            f.write("")

    for alias, cn in aliases.items():
        cpath = tmp_path / "dependencies" / cn
        if not cpath.is_dir():
            continue
        apath = tmp_path / "dependencies" / alias
        assert not apath.is_dir()
        os.symlink(cpath, apath)

    return component_dirs, other_dirs


@patch("commodore.dependency_mgmt._read_components")
@patch("commodore.dependency_mgmt._discover_components")
def test_register_components(
    patch_discover, patch_read, config: Config, tmp_path: Path
):
    component_dirs, other_dirs = _setup_register_components(tmp_path)
    patch_discover.return_value = (component_dirs, {})
    patch_read.return_value = {
        cn: DependencySpec(f"https://fake.repo.url/{cn}.git", "master", "")
        for cn in component_dirs
    }

    dependency_mgmt.register_components(config)

    component_names = config.get_components().keys()
    for c in component_dirs:
        assert c in component_names
    for c in other_dirs:
        assert c not in component_names


@patch("commodore.dependency_mgmt._read_components")
@patch("commodore.dependency_mgmt._discover_components")
def test_register_components_and_aliases(
    patch_discover, patch_read, config: Config, tmp_path: Path
):
    alias_data = {"fooer": "foo"}
    component_dirs, other_dirs = _setup_register_components(
        tmp_path, aliases=alias_data
    )
    patch_discover.return_value = (component_dirs, alias_data)
    patch_read.return_value = {
        cn: DependencySpec(f"https://fake.repo.url/{cn}.git", "master", "")
        for cn in component_dirs
    }
    patch_read.return_value["fooer"] = patch_read.return_value["foo"]

    dependency_mgmt.register_components(config)

    component_names = config.get_components().keys()
    for c in component_dirs:
        assert c in component_names
    for c in other_dirs:
        assert c not in component_names

    aliases = config.get_component_aliases()
    for alias, cn in alias_data.items():
        if cn in component_dirs:
            assert alias in aliases
            assert aliases[alias] == cn
        else:
            assert alias not in aliases


@patch("commodore.dependency_mgmt._read_components")
@patch("commodore.dependency_mgmt._discover_components")
def test_register_components_and_aliases_raises(
    patch_discover, patch_read, config: Config, tmp_path: Path
):
    alias_data = {"fooer": "foo"}
    component_dirs, other_dirs = _setup_register_components(tmp_path)
    patch_discover.return_value = (component_dirs, alias_data)
    patch_read.return_value = {
        cn: DependencySpec(f"https://fake.repo.url/{cn}.git", "master", "")
        for cn in component_dirs
    }
    patch_read.return_value["fooer"] = patch_read.return_value["foo"]

    with pytest.raises(Exception) as excinfo:
        dependency_mgmt.register_components(config)

    assert "Missing alias checkout for 'fooer as foo'" in str(excinfo.value)


@patch("commodore.dependency_mgmt._read_components")
@patch("commodore.dependency_mgmt._discover_components")
def test_register_unknown_components(
    patch_discover, patch_read, config: Config, tmp_path: Path, capsys
):
    component_dirs, other_dirs = _setup_register_components(tmp_path)
    unknown_components = ["qux", "quux"]
    component_dirs.extend(unknown_components)
    patch_discover.return_value = (component_dirs, {})
    patch_read.return_value = {
        cn: DependencySpec(f"https://fake.repo.url/{cn}.git", "master", "")
        for cn in component_dirs
    }

    dependency_mgmt.register_components(config)

    captured = capsys.readouterr()
    for cn in unknown_components:
        assert f"Skipping registration of component {cn}" in captured.out


@patch("commodore.dependency_mgmt._read_components")
@patch("commodore.dependency_mgmt._discover_components")
def test_register_dangling_aliases(
    patch_discover, patch_read, config: Config, tmp_path: Path, capsys
):
    # add some dangling aliases
    alias_data = {"quxer": "qux", "quuxer": "quux"}
    # generate expected output
    should_miss = sorted(set(alias_data.keys()))
    # add an alias that should work
    alias_data["bazzer"] = "baz"
    component_dirs, other_dirs = _setup_register_components(
        tmp_path, aliases=alias_data
    )

    patch_discover.return_value = (component_dirs, alias_data)
    patch_read.return_value = {
        cn: DependencySpec(f"https://fake.repo.url/{cn}.git", "master", "")
        for cn in component_dirs
    }
    patch_read.return_value["bazzer"] = patch_read.return_value["baz"]

    dependency_mgmt.register_components(config)

    captured = capsys.readouterr()
    assert (
        f"Dropping alias(es) {should_miss} with missing component(s)." in captured.out
    )


@pytest.mark.parametrize(
    "libname,expected",
    [
        ("test-component.libsonnet", ""),
        ("test-component-lib.libsonnet", ""),
        (
            "lib.libsonnet",
            "Component 'test-component' uses invalid component library name 'lib.libsonnet'. "
            + "Consider using a library alias.",
        ),
    ],
)
def test_validate_component_library_name(tmp_path: Path, libname: str, expected: str):
    if expected == "":
        lpath = Path(tmp_path / "lib" / libname)
        r = dependency_mgmt.validate_component_library_name("test-component", lpath)
        assert lpath == r

    else:
        with pytest.raises(click.ClickException) as e:
            dependency_mgmt.validate_component_library_name(
                "test-component", Path(tmp_path / "lib" / libname)
            )

        assert expected in str(e.value)


@pytest.mark.parametrize(
    "cluster_params,aliases,expected",
    [
        (
            {
                "components": {
                    "component-1": {
                        "url": "https://example.com/component-1.git",
                        "version": "v1.2.3",
                    },
                    "component-2": {
                        "url": "https://example.com/component-2.git",
                        "version": "v4.5.6",
                    },
                    "component-3": {
                        "url": "https://example.com/component-3.git",
                        "version": "v7.8.9",
                    },
                },
            },
            {},
            "",
        ),
        (
            {
                "components": {
                    "component-1": {
                        "url": "https://example.com/component-1.git",
                        "version": "v1.2.3",
                    },
                    "component_1": {"version": "feat/test"},
                    "component-2": {
                        "url": "https://example.com/component-2.git",
                        "version": "v4.5.6",
                    },
                    "component-3": {
                        "url": "https://example.com/component-3.git",
                        "version": "v7.8.9",
                    },
                },
            },
            {},
            "Version override specified for component 'component_1' which has no URL",
        ),
        (
            {
                "components": {
                    "component-1": {
                        "url": "https://example.com/component-1.git",
                        "version": "v1.2.3",
                    },
                    "component_1": {"version": "feat/test"},
                    "component-2": {
                        "url": "https://example.com/component-2.git",
                        "version": "v4.5.6",
                    },
                    "component_2": {"version": "feat/test2"},
                    "component-3": {
                        "url": "https://example.com/component-3.git",
                        "version": "v7.8.9",
                    },
                },
            },
            {},
            "Version overrides specified for component 'component_1' and component 'component_2' which have no URL",
        ),
        (
            {
                "components": {
                    "component-1": {
                        "url": "https://example.com/component-1.git",
                        "version": "v1.2.3",
                    },
                },
                "packages": {
                    "package-1": {
                        "version": "v1.0.0",
                    }
                },
            },
            {},
            "Version override specified for package 'package-1' which has no URL",
        ),
        (
            {
                "components": {
                    "component-1": {
                        "version": "v1.2.3",
                    },
                },
                "packages": {
                    "package-1": {
                        "version": "v1.0.0",
                    }
                },
            },
            {},
            "Version overrides specified for component 'component-1' and package 'package-1' which have no URL",
        ),
        (
            {
                "components": {
                    "component-1": {
                        "version": "v1.2.3",
                    },
                    "component-2": {
                        "version": "v1.2.3",
                    },
                },
                "packages": {
                    "package-1": {
                        "version": "v1.0.0",
                    }
                },
            },
            {},
            "Version overrides specified for component 'component-1', "
            + "component 'component-2', and package 'package-1' which have no URL",
        ),
        (
            {
                "components": {
                    "component-1": {
                        "version": "v1.2.3",
                        "url": "https://example.com/component-1.git",
                    },
                    "component-2": {
                        "version": "v1.2.3",
                        "url": "https://example.com/component-2.git",
                    },
                    "alias-1": {
                        "version": "v1.2.4",
                        "url": "https://example.com/component-1-fork.git",
                    },
                    "alias-2": {
                        "version": "v1.2.4",
                    },
                },
            },
            {
                "alias-1": "component-1",
                "alias-2": "component-2",
            },
            "",
        ),
        (
            {
                "components": {
                    "alias-1": {
                        "version": "v1.2.4",
                        "url": "https://example.com/component-1-fork.git",
                    },
                },
            },
            {
                "alias-1": "component-1",
            },
            "Version override specified for component 'component-1' (imported as alias-1) which has no URL",
        ),
    ],
)
def test_verify_component_version_overrides(
    cluster_params: dict, aliases: dict, expected: str
):
    if expected == "":
        dependency_mgmt.verify_version_overrides(cluster_params, aliases)
    else:
        with pytest.raises(click.ClickException) as e:
            dependency_mgmt.verify_version_overrides(cluster_params, aliases)

        assert expected in str(e)


def _setup_packages(
    upstream_path: Path, packages: list[str]
) -> dict[str, DependencySpec]:
    package_specs = {}

    for p in packages:
        _setup_package_remote(p, upstream_path / f"{p}.git")
        url = f"file://{upstream_path}/{p}.git"
        version = "master"
        package_specs[p] = DependencySpec(url, version, "")

    return package_specs


@patch.object(dependency_mgmt, "_read_packages")
@patch.object(dependency_mgmt, "_discover_packages")
@pytest.mark.parametrize(
    "packages",
    [
        ["test"],
        ["foo", "bar"],
    ],
)
def test_fetch_packages(
    discover_pkgs, read_pkgs, tmp_path: Path, config: Config, packages: list[str]
):
    discover_pkgs.return_value = packages
    read_pkgs.return_value = _setup_packages(tmp_path / "upstream", packages)

    dependency_mgmt.fetch_packages(config)

    for p in packages:
        pkg_dir = config.inventory.package_dir(p)
        pkg_file = pkg_dir / f"{p}.yml"
        assert pkg_dir.is_dir()
        assert pkg_file.is_file()
        with open(pkg_file, "r") as f:
            fcontents = yaml.safe_load(f)
            assert "parameters" in fcontents
            params = fcontents["parameters"]
            assert p in params
            assert params[p] == "testing"


@patch.object(dependency_mgmt, "_read_packages")
@patch.object(dependency_mgmt, "_discover_packages")
def test_fetch_packages_raises(
    discover_pkgs, read_pkgs, tmp_path: Path, config: Config
):
    packages = ["foo"]
    discover_pkgs.return_value = packages
    read_pkgs.return_value = _setup_packages(tmp_path / "upstream", packages)

    dependency_mgmt.fetch_packages(config)

    with open(
        config.get_packages()["foo"].repository_dir / "foo.yml", "w", encoding="utf-8"
    ) as f:
        f.write("foo: bar\n")

    config._dependency_repos.clear()
    config._packages.clear()

    with pytest.raises(click.ClickException) as excinfo:
        dependency_mgmt.fetch_packages(config)

    assert (
        "Package foo has uncommitted changes. Please specify `--force` to discard them"
        in str(excinfo.value)
    )


@patch.object(dependency_mgmt, "_read_packages")
@patch.object(dependency_mgmt, "_discover_packages")
@pytest.mark.parametrize("packages", [[], ["test"], ["foo", "bar"]])
def test_register_packages(
    discover_pkgs, read_pkgs, tmp_path: Path, config: Config, packages: list[str]
):
    discover_pkgs.return_value = packages
    read_pkgs.return_value = _setup_packages(tmp_path / "upstream", packages)
    for p in packages:
        git.Repo.clone_from(
            f"file://{tmp_path}/upstream/{p}.git", package_dependency_dir(tmp_path, p)
        )

    dependency_mgmt.register_packages(config)

    pkgs = config.get_packages()
    assert sorted(pkgs.keys()) == sorted(packages)


@patch.object(dependency_mgmt, "_read_packages")
@patch.object(dependency_mgmt, "_discover_packages")
def test_register_packages_skip_nonexistent(
    discover_pkgs, read_pkgs, tmp_path: Path, config: Config, capsys
):
    packages = ["foo", "bar"]
    discover_pkgs.return_value = packages
    read_pkgs.return_value = _setup_packages(tmp_path / "upstream", packages)
    git.Repo.clone_from(
        f"file://{tmp_path}/upstream/foo.git", package_dependency_dir(tmp_path, "foo")
    )

    dependency_mgmt.register_packages(config)

    pkgs = config.get_packages()
    assert list(pkgs.keys()) == ["foo"]

    captured = capsys.readouterr()

    assert (
        "Skipping registration of package 'bar': repo is not available" in captured.out
    )


def test_fetch_component_raises_clickexception(tmp_path: Path, config: Config):
    deps = setup_components_upstream(tmp_path, ["test-component"], {})
    cspec = deps["test-component"]
    cspec.version = "foo"
    cdep = config.register_dependency_repo(cspec.url)
    component = Component(
        "test-component",
        work_dir=tmp_path,
        dependency=cdep,
        sub_path=cspec.path,
        version=cspec.version,
    )
    with pytest.raises(click.ClickException) as exc:
        dependency_mgmt.fetch_component(config, [component])

    assert (
        "while fetching component test-component: Failed to checkout revision 'foo'"
        in str(exc.value)
    )


def test_setup_alias_raises_clickexception(tmp_path: Path, config: Config):
    deps = setup_components_upstream(
        tmp_path, ["test-component"], {"test-alias": "test-component"}
    )
    aspec = deps["test-alias"]
    aspec.version = "foo"
    adep = config.register_dependency_repo(aspec.url)
    component = Component(
        "test-component",
        work_dir=tmp_path,
        dependency=adep,
        sub_path=aspec.path,
        version="master",
    )
    component.register_alias("test-alias", aspec.version, adep)
    with pytest.raises(click.ClickException) as exc:
        dependency_mgmt.setup_alias(config, [("test-alias", component)])

    assert (
        "while setting up component instance test-alias: Failed to checkout revision 'foo'"
        in str(exc.value)
    )


def test_fetch_package_raises_clickexception(tmp_path: Path, config: Config):
    deps = _setup_packages(tmp_path / "upstream", ["test-package"])
    pspec = deps["test-package"]
    pdep = config.register_dependency_repo(pspec.url)
    pkg = Package(
        "test-package",
        dependency=pdep,
        target_dir=package_dependency_dir(config.work_dir, "test-package"),
        version="foo",
        sub_path=pspec.path,
    )

    with pytest.raises(click.ClickException) as exc:
        dependency_mgmt.fetch_package(config, [("test-package", pkg)])

    assert (
        "while fetching package test-package: Failed to checkout revision 'foo'"
        in str(exc.value)
    )
