"""
Unit-tests for dependency management
"""

import os
import click
import git
import pytest
import json
from unittest.mock import patch
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from commodore import dependency_mgmt
from commodore.config import Config
from commodore.component import Component
from commodore.inventory import Inventory


def setup_components_upstream(tmp_path: Path, components: Iterable[str]):
    # Prepare minimum component directories
    upstream = tmp_path / "upstream"
    component_urls = {}
    component_versions = {}
    for component in components:
        repo_path = upstream / component
        component_urls[component] = f"file://#{repo_path.resolve()}"
        component_versions[component] = None
        repo = git.Repo.init(repo_path)

        class_dir = repo_path / "class"
        class_dir.mkdir(parents=True, exist_ok=True)
        (class_dir / "defaults.yml").touch(exist_ok=True)
        (class_dir / f"{component}.yml").touch(exist_ok=True)

        repo.index.add(["class/defaults.yml", f"class/{component}.yml"])
        repo.index.commit("component defaults")

    return component_urls, component_versions


@pytest.fixture
def data(tmp_path):
    """
    Setup test data
    """

    return Config(
        tmp_path,
        api_url="https://syn.example.com",
        api_token="token",
    )


def test_create_component_symlinks_fails(data: Config, tmp_path: Path):
    component = Component("my-component", work_dir=tmp_path)
    with pytest.raises(click.ClickException) as e:
        dependency_mgmt.create_component_symlinks(data, component)

    assert "Source does not exist" in str(e.value)


def setup_mock_component(tmp_path: Path, name="my-component") -> Component:
    component = Component(name, work_dir=tmp_path)
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


def test_create_component_symlinks(capsys, data: Config, tmp_path):
    component = setup_mock_component(tmp_path)
    inv = Inventory(work_dir=tmp_path)
    inv.ensure_dirs()

    dependency_mgmt.create_component_symlinks(data, component)

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


@pytest.mark.parametrize(
    "libaliases,expected_paths,stdout",
    [
        (None, [], ""),
        ({}, [], ""),
        (
            {"foo.libsonnet": "my-component.libjsonnet"},
            ["dependencies/lib/foo.libsonnet"],
            "",
        ),
        (
            {"foo.libsonnet": "bar.libjsonnet"},
            [],
            " > [WARN] 'my-component' template library alias 'foo.libsonnet' "
            + "refers to nonexistent template library 'bar.libjsonnet'",
        ),
        (
            {
                "foo.libsonnet": "my-component.libjsonnet",
                "bar.libsonnet": "my-component.libsonnet",
            },
            ["dependencies/lib/foo.libsonnet"],
            " > [WARN] 'my-component' template library alias 'bar.libsonnet' "
            + "refers to nonexistent template library 'my-component.libsonnet'",
        ),
    ],
)
def test_create_component_library_aliases_single_component(
    capsys,
    tmp_path: Path,
    data: Config,
    libaliases: Optional[Dict],
    expected_paths: Iterable[str],
    stdout: str,
):
    component = setup_mock_component(tmp_path)
    data.register_component(component)
    inv = Inventory(work_dir=tmp_path)
    inv.ensure_dirs()

    cluster_params = {
        component.parameters_key: {},
        "components": {
            component.name: {
                "url": f"https://example.com/{component.name}.git",
                "version": "master",
            }
        },
    }
    if libaliases is not None:
        cluster_params[component.parameters_key] = {
            "_metadata": {
                "library_aliases": libaliases,
            },
        }

    dependency_mgmt.create_component_library_aliases(data, cluster_params)

    expected_aliases = [(tmp_path / path, "lib") for path in expected_paths]
    for path, marker in expected_aliases:
        # Ensure symlinks exist
        assert path.is_symlink()
        # Ensure symlink targets exist
        assert path.resolve().is_file()
        # Ensure symlinked file contains correct marker content
        with open(path) as f:
            fcontents = f.readlines()
            assert fcontents[0] == marker

    captured = capsys.readouterr()
    assert stdout in captured.out


@pytest.mark.parametrize(
    "tc1_libalias,tc2_libalias,tc3_libalias,err",
    [
        ({}, {}, {}, None),
        (
            {"foo.libsonnet": "tc1.libjsonnet"},
            {},
            {},
            None,
        ),
        (
            {},
            {"foo.libsonnet": "tc2.libjsonnet"},
            {},
            None,
        ),
        (
            {"foo.libsonnet": "tc1.libjsonnet"},
            {"foo.libsonnet": "tc2.libjsonnet"},
            {},
            "Components 'tc1' and 'tc2' both define component library alias 'foo.libsonnet'",
        ),
        (
            {"foo.libsonnet": "tc1.libjsonnet"},
            {"foo.libsonnet": "tc2.libjsonnet"},
            {"foo.libsonnet": "tc3.libjsonnet"},
            "Components 'tc1', 'tc2', and 'tc3' all define component library alias 'foo.libsonnet'",
        ),
        (
            {"tc2-fake.libsonnet": "tc1.libjsonnet"},
            {},
            {},
            "Invalid alias prefix 'tc2' for template library alias of component 'tc1'",
        ),
    ],
)
def test_create_component_library_aliases_multiple_component(
    tmp_path: Path,
    data: Config,
    tc1_libalias: Dict[str, str],
    tc2_libalias: Dict[str, str],
    tc3_libalias: Dict[str, str],
    err: Optional[str],
):
    c1 = setup_mock_component(tmp_path, name="tc1")
    c2 = setup_mock_component(tmp_path, name="tc2")
    c3 = setup_mock_component(tmp_path, name="tc3")

    data.register_component(c1)
    data.register_component(c2)
    data.register_component(c3)

    cluster_params = {
        c1.parameters_key: {
            "_metadata": {"library_aliases": tc1_libalias},
        },
        c2.parameters_key: {
            "_metadata": {"library_aliases": tc2_libalias},
        },
        c3.parameters_key: {
            "_metadata": {"library_aliases": tc3_libalias},
        },
        "components": {
            "tc1": {
                "url": "https://example.com/tc1.git",
                "version": "master",
            },
            "tc2": {
                "url": "https://example.com/tc2.git",
                "version": "master",
            },
            "tc3": {
                "url": "https://example.com/tc3.git",
                "version": "master",
            },
        },
    }

    if err:
        with pytest.raises(click.ClickException) as e:
            dependency_mgmt.create_component_library_aliases(data, cluster_params)

        assert err in str(e.value)


def _setup_mock_inventory(patch_inventory, aliases={}):
    components = {
        "test-component": {
            "url": "https://github.com/projectsyn/component-test-component.git",
            "version": "master",
        },
        "other-component": {
            "url": "ssh://git@git.acme.com/some/component.git",
        },
        "third-component": {
            "url": "https://github.com/projectsyn/component-third-component.git",
            "version": "feat/test",
        },
    }
    assert set(aliases.keys()) <= set(components.keys())
    applications = list(components.keys())
    for c, a in aliases.items():
        applications.append(f"{c} as {a}")
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

    def inv(inventory_dir, key="nodes"):
        return mock_inventory[key]

    patch_inventory.side_effect = inv

    return mock_inventory["nodes"]["cluster"]["parameters"]["components"]


@patch.object(dependency_mgmt, "kapitan_inventory")
def test_read_components(patch_inventory, data: Config):
    components = _setup_mock_inventory(patch_inventory)
    component_urls, component_versions = dependency_mgmt._read_components(
        data, ["test-component"]
    )

    # check that exactly 'test-component' is discovered
    assert {"test-component"} == set(component_urls.keys())
    assert components["test-component"]["url"] == component_urls["test-component"]
    assert (
        components["test-component"]["version"] == component_versions["test-component"]
    )


@patch.object(dependency_mgmt, "kapitan_inventory")
def test_read_components_multiple(patch_inventory, data: Config):
    components = _setup_mock_inventory(patch_inventory)
    component_urls, component_versions = dependency_mgmt._read_components(
        data, components.keys()
    )
    # check that exactly 'test-component' is discovered
    assert set(components.keys()) == set(component_urls.keys())
    assert set(components.keys()) == set(component_versions.keys())
    assert all(components[cn]["url"] == component_urls[cn] for cn in components.keys())
    assert all(
        components[cn].get("version", None) == component_versions[cn]
        for cn in components.keys()
    )


@patch("commodore.dependency_mgmt.kapitan_inventory")
def test_read_components_deprecation(
    patch_inventory, data: Config, tmp_path: Path, capsys
):
    components = _setup_mock_inventory(patch_inventory)

    _ = dependency_mgmt._read_components(data, components.keys())

    data.print_deprecation_notices()
    captured = capsys.readouterr()

    # We split and join captured.out to revert the formatting done by
    # print_deprecation_notices().
    assert (
        "Component other-component doesn't have a version specified. "
        + "See https://syn.tools/commodore/reference/deprecation-notices.html"
        + "#_components_without_versions for more details."
    ) in " ".join(captured.out.split())


@pytest.mark.parametrize(
    "components,ckeys,exctext",
    [
        ({}, [], "Component list ('parameters.components') missing"),
        (
            {"components": {"a": {"url": "a_url"}}},
            ["b"],
            "Unknown component 'b'. Please add it to 'parameters.components'",
        ),
        (
            {"components": {"a": {"version": "a_version"}}},
            ["a"],
            "No url for component 'a' configured",
        ),
    ],
)
@patch("commodore.dependency_mgmt.kapitan_inventory")
def test_read_components_exc(
    patch_inventory,
    data: Config,
    tmp_path: Path,
    capsys,
    components,
    ckeys,
    exctext,
):
    patch_inventory.return_value = {
        data.inventory.bootstrap_target: {"parameters": components},
    }

    with pytest.raises(click.ClickException) as exc_info:
        _ = dependency_mgmt._read_components(data, ckeys)

    assert exc_info.value.args[0] == exctext


@patch.object(dependency_mgmt, "kapitan_inventory")
def test_discover_components(patch_inventory, data: Config):
    component_inv = _setup_mock_inventory(patch_inventory)

    components, aliases = dependency_mgmt._discover_components(data)
    assert components == sorted(component_inv.keys())
    assert sorted(aliases.keys()) == components
    assert all(k == v for k, v in aliases.items())


@patch.object(dependency_mgmt, "kapitan_inventory")
def test_discover_components_aliases(patch_inventory, data: Config):
    expected_aliases = {"other-component": "aliased"}
    component_inv = _setup_mock_inventory(patch_inventory, expected_aliases)

    components, aliases = dependency_mgmt._discover_components(data)
    assert components == sorted(component_inv.keys())
    assert set(components + list(expected_aliases.values())) == set(aliases.keys())
    assert set(aliases.values()) == set(components)
    assert aliases["aliased"] == "other-component"


@pytest.mark.parametrize(
    "components,expected",
    [
        ([], ""),
        (["a"], "'a'"),
        (["a", "b"], "'a' and 'b'"),
        # Verify that Oxford comma is used in lists with >= items
        (
            ["a", "b", "c"],
            "'a', 'b', and 'c'",
        ),
        (
            ["a", "b", "c", "d", "e"],
            "'a', 'b', 'c', 'd', and 'e'",
        ),
    ],
)
def test_format_component_list(components, expected):
    assert dependency_mgmt._format_component_list(components) == expected


@pytest.mark.parametrize(
    "expected_aliases,expected_exception_msg",
    [
        (
            {"other-component": "aliased", "third-component": "aliased"},
            "Duplicate component alias 'aliased': components "
            + "'other-component' and 'third-component' are aliased to 'aliased'",
        ),
        (
            {"other-component": "third-component", "third-component": "aliased"},
            "Component 'other-component' aliases existing component 'third-component'",
        ),
        (
            {
                "test-component": "third-component",
                "other-component": "third-component",
                "third-component": "aliased",
            },
            "Components 'other-component' and 'test-component' alias "
            + "existing component 'third-component'",
        ),
    ],
)
@patch.object(dependency_mgmt, "kapitan_inventory")
def test_discover_components_duplicate_aliases(
    patch_inventory, data: Config, expected_aliases, expected_exception_msg
):
    _setup_mock_inventory(patch_inventory, expected_aliases)

    with pytest.raises(KeyError) as e:
        dependency_mgmt._discover_components(data)

    assert e.value.args[0] == expected_exception_msg


@patch("commodore.dependency_mgmt._read_components")
@patch("commodore.dependency_mgmt._discover_components")
def test_fetch_components(patch_discover, patch_read, data: Config, tmp_path: Path):
    components = ["component-one", "component-two"]
    patch_discover.return_value = (components, {})
    patch_read.return_value = setup_components_upstream(tmp_path, components)

    dependency_mgmt.fetch_components(data)

    for component in components:
        assert component in data._components
        assert (
            tmp_path / "inventory" / "classes" / "components" / f"{component}.yml"
        ).is_symlink()
        assert (
            tmp_path / "inventory" / "classes" / "defaults" / f"{component}.yml"
        ).is_symlink()
        assert (tmp_path / "dependencies" / component).is_dir()


@patch("commodore.dependency_mgmt._read_components")
@patch("commodore.dependency_mgmt._discover_components")
def test_fetch_components_is_minimal(
    patch_discover, patch_urls, data: Config, tmp_path: Path
):
    components = ["component-one", "component-two"]
    other_components = ["component-three", "component-four"]
    patch_discover.return_value = (components, {})
    patch_urls.return_value = setup_components_upstream(tmp_path, components)
    # Setup upstreams for components which are not included
    extra_urls, extra_versions = setup_components_upstream(tmp_path, other_components)
    for cn in extra_urls.keys():
        patch_urls.return_value[0][cn] = extra_urls[cn]
        patch_urls.return_value[1][cn] = extra_versions[cn]

    dependency_mgmt.fetch_components(data)

    for component in components:
        assert component in data._components
        assert (
            tmp_path / "inventory" / "classes" / "components" / f"{component}.yml"
        ).is_symlink()
        assert (
            tmp_path / "inventory" / "classes" / "defaults" / f"{component}.yml"
        ).is_symlink()
        assert (tmp_path / "dependencies" / component).is_dir()

    for component in other_components:
        assert component not in data._components
        assert not (tmp_path / "dependencies" / component).exists()


def test_write_jsonnetfile(data: Config, tmp_path: Path):
    data.register_component(Component("test-component", work_dir=tmp_path))
    data.register_component(Component("test-component-2", work_dir=tmp_path))
    dirs = [
        "dependencies/test-component",
        "dependencies/test-component-2",
        "dependencies/lib",
    ]

    file = tmp_path / "jsonnetfile.json"

    dependency_mgmt.write_jsonnetfile(file, dependency_mgmt.jsonnet_dependencies(data))

    with open(file) as jf:
        jf_string = jf.read()
        assert jf_string[-1] == "\n"
        jf_contents = json.loads(jf_string)
        assert jf_contents["version"] == 1
        assert jf_contents["legacyImports"]
        deps = jf_contents["dependencies"]
        for dep in deps:
            assert dep["source"]["local"]["directory"] in dirs


def test_inject_essential_libraries(tmp_path: Path):
    file = tmp_path / "jsonnetfile.json"
    dependency_mgmt.write_jsonnetfile(file, [])

    dependency_mgmt.inject_essential_libraries(file)

    with open(file) as jf:
        jf_string = jf.read()
        assert jf_string[-1] == "\n"
        jf_contents = json.loads(jf_string)
        assert jf_contents["version"] == 1
        assert jf_contents["legacyImports"]
        deps = jf_contents["dependencies"]
        assert len(deps) == 1
        assert (
            deps[0]["source"]["git"]["remote"]
            == "https://github.com/bitnami-labs/kube-libsonnet"
        )
        assert deps[0]["version"] == "v1.19.0"


def test_clear_jsonnet_lock_file(tmp_path: Path):
    jsonnetfile = tmp_path / "jsonnetfile.json"
    jsonnet_lock = tmp_path / "jsonnetfile.lock.json"
    with open(jsonnetfile, "w") as jf:
        json.dump(
            {
                "version": 1,
                "dependencies": [
                    {
                        "source": {
                            "git": {
                                "remote": "https://github.com/brancz/kubernetes-grafana.git",
                                "subdir": "grafana",
                            }
                        },
                        "version": "master",
                    }
                ],
                "legacyImports": True,
            },
            jf,
        )
    with open(jsonnet_lock, "w") as jl:
        json.dump(
            {
                "version": 1,
                "dependencies": [
                    {
                        "source": {
                            "git": {
                                "remote": "https://github.com/brancz/kubernetes-grafana.git",
                                "subdir": "grafana",
                            }
                        },
                        "version": "57b4365eacda291b82e0d55ba7eec573a8198dda",
                        "sum": "92DWADwGjnCfpZaL7Q07C0GZayxBziGla/O03qWea34=",
                    }
                ],
                "legacyImports": True,
            },
            jl,
        )
    dependency_mgmt.fetch_jsonnet_libraries(tmp_path)

    assert jsonnet_lock.is_file()
    with open(jsonnet_lock, "r") as file:
        data = json.load(file)
        assert (
            data["dependencies"][0]["version"]
            != "57b4365eacda291b82e0d55ba7eec573a8198dda"
        )


def _setup_register_components(tmp_path: Path):
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

    return component_dirs, other_dirs


@patch("commodore.dependency_mgmt._discover_components")
def test_register_components(patch_discover, data: Config, tmp_path: Path):
    component_dirs, other_dirs = _setup_register_components(tmp_path)
    patch_discover.return_value = (component_dirs, {})

    dependency_mgmt.register_components(data)

    component_names = data.get_components().keys()
    for c in component_dirs:
        assert c in component_names
    for c in other_dirs:
        assert c not in component_names


@patch("commodore.dependency_mgmt._discover_components")
def test_register_components_and_aliases(patch_discover, data: Config, tmp_path: Path):
    component_dirs, other_dirs = _setup_register_components(tmp_path)
    alias_data = {"fooer": "foo"}
    patch_discover.return_value = (component_dirs, alias_data)

    dependency_mgmt.register_components(data)

    component_names = data.get_components().keys()
    for c in component_dirs:
        assert c in component_names
    for c in other_dirs:
        assert c not in component_names

    aliases = data.get_component_aliases()
    for alias, cn in alias_data.items():
        if cn in component_dirs:
            assert alias in aliases
            assert aliases[alias] == cn
        else:
            assert alias not in aliases


@patch("commodore.dependency_mgmt._discover_components")
def test_register_unknown_components(
    patch_discover, data: Config, tmp_path: Path, capsys
):
    component_dirs, other_dirs = _setup_register_components(tmp_path)
    unknown_components = ["qux", "quux"]
    component_dirs.extend(unknown_components)
    patch_discover.return_value = (component_dirs, {})

    dependency_mgmt.register_components(data)

    captured = capsys.readouterr()
    for cn in unknown_components:
        assert f"Skipping registration of component {cn}" in captured.out


@patch("commodore.dependency_mgmt._discover_components")
def test_register_dangling_aliases(
    patch_discover, data: Config, tmp_path: Path, capsys
):
    component_dirs, other_dirs = _setup_register_components(tmp_path)
    # add some dangling aliases
    alias_data = {"quxer": "qux", "quuxer": "quux"}
    # generate expected output
    should_miss = sorted(set(alias_data.keys()))
    # add an alias that should work
    alias_data["bazzer"] = "baz"

    patch_discover.return_value = (component_dirs, alias_data)

    dependency_mgmt.register_components(data)

    captured = capsys.readouterr()
    assert (
        f"Dropping alias(es) {should_miss} with missing component(s)." in captured.out
    )


@pytest.mark.parametrize(
    "libname,expected",
    [
        ("test-component.libsonnet", []),
        ("test-component-lib.libsonnet", []),
        (
            "lib.libsonnet",
            [
                "Component 'test-component' uses component library name lib.libsonnet "
                + "which isn't prefixed with the component's name."
            ],
        ),
    ],
)
def test_validate_component_library_name(
    tmp_path: Path, data: Config, libname: str, expected: List[str]
):
    dependency_mgmt.validate_component_library_name(
        data, "test-component", Path(tmp_path / "lib" / libname)
    )

    assert len(data._deprecation_notices) == len(expected)
    if len(expected) == 1:
        assert expected[0] in data._deprecation_notices[0]


@pytest.mark.parametrize(
    "cluster_params,expected",
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
            "Version overrides specified for components 'component_1' and 'component_2' which have no URL",
        ),
    ],
)
def test_verify_component_version_overrides(cluster_params: Dict, expected: str):
    if expected == "":
        dependency_mgmt.verify_component_version_overrides(cluster_params)
    else:
        with pytest.raises(click.ClickException) as e:
            dependency_mgmt.verify_component_version_overrides(cluster_params)

        assert expected in str(e)
