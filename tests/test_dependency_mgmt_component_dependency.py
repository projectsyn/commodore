import copy

from pathlib import Path
from typing import Optional

import click
import pytest
import semver

from commodore.config import Config
from commodore.component import Component
from commodore.multi_dependency import MultiDependency

from commodore.dependency_mgmt import component_dependency


def _make_dep(
    name: str,
    url: str,
    instances: list[str] = ["test-component"],
    path: Optional[str] = None,
    minverspec: Optional[str] = None,
    requiredif: Optional[list[str]] = None,
):
    mandatory = False
    if not requiredif:
        mandatory = True
    minversion = None
    if minverspec:
        try:
            minversion = semver.Version.parse(minverspec)
        except ValueError:
            minversion = semver.Version.parse(minverspec[1:])

    return component_dependency.ComponentDependency(
        name,
        instances,
        url,
        path,
        minverspec,
        minversion,
        None,
        mandatory,
        requiredif or [],
    )


@pytest.mark.parametrize(
    "depname,depspec,expected",
    [
        (
            "argocd",
            {"url": "https://github.com/projectsyn/component-argocd.git"},
            _make_dep("argocd", "https://github.com/projectsyn/component-argocd.git"),
        ),
        (
            "argocd",
            {
                "url": "https://github.com/projectsyn/component-argocd.git",
                "minversion": "v1.0.0",
            },
            _make_dep(
                "argocd",
                "https://github.com/projectsyn/component-argocd.git",
                minverspec="v1.0.0",
            ),
        ),
        (
            "argocd",
            {
                "url": "https://github.com/projectsyn/component-argocd.git",
                "requiredif": "facts.distribution == 'openshift4'",
            },
            _make_dep(
                "argocd",
                "https://github.com/projectsyn/component-argocd.git",
                requiredif=["facts.distribution == 'openshift4'"],
            ),
        ),
    ],
)
def test_component_dependency_parse(
    depname: str,
    depspec: dict[str, str],
    expected: component_dependency.ComponentDependency,
):
    dep = component_dependency.ComponentDependency.parse(
        "test-component", depname, depspec
    )
    assert dep == expected


@pytest.mark.parametrize(
    "depname,depspec,expected_error",
    [
        ("argocd", {}, "Error parsing dependency specification: field 'url' missing"),
        (
            "argocd",
            {
                "url": "https://github.com/projectsyn/component-argocd.git",
                "minversion": "foo",
            },
            "Error parsing dependency specification: foo is not valid SemVer string",
        ),
    ],
)
def test_component_dependency_parse_error(
    depname: str, depspec: dict[str, str], expected_error: str
):

    with pytest.raises(component_dependency.ComponentDependencyParseError) as e:
        component_dependency.ComponentDependency.parse(
            "test-component", depname, depspec
        )

    assert expected_error in str(e)


@pytest.mark.parametrize(
    "d1_min,d2_min,expected_min",
    [
        (None, None, None),
        (None, "v1.0.0", "v1.0.0"),
        ("v1.2.3", "v1.0.0", "v1.2.3"),
        ("v1.0.0", "v1.2.3", "v1.2.3"),
    ],
)
def test_component_dependency_update(
    d1_min: Optional[str], d2_min: Optional[str], expected_min: Optional[str]
):
    d1 = _make_dep(
        "argocd",
        "https://github.com/projectsyn/component-argocd.git",
        instances=["cilium"],
        minverspec=d1_min,
    )
    d2 = _make_dep(
        "argocd",
        "https://github.com/projectsyn/component-argocd.git",
        instances=["rook-ceph"],
        minverspec=d2_min,
    )
    d1.update(d2)
    assert d1.minverspec == expected_min
    if expected_min:
        assert d1.minversion == semver.Version.parse(expected_min[1:])
    assert d1.instances == ["cilium", "rook-ceph"]


@pytest.mark.parametrize(
    "d1,d2,expected_error",
    [
        (
            {"name": "argocd"},
            {"name": "foo"},
            "Cannot merge ComponentDependency objects with different names: argocd, foo",
        ),
        (
            {
                "name": "argocd",
                "url": "https://github.com/projectsyn/component-argocd.git",
            },
            {
                "name": "argocd",
                "url": "https://github.com/projectsyn/component-argocd",
            },
            "Cannot merge ComponentDependency objects with same name but different URLs: "
            + "https://github.com/projectsyn/component-argocd.git, https://github.com/projectsyn/component-argocd",
        ),
        (
            {
                "name": "argocd",
                "url": "https://github.com/projectsyn/component-argocd.git",
            },
            {
                "name": "argocd",
                "url": "https://github.com/projectsyn/component-argocd.git",
                "path": "foobar",
            },
            "Cannot merge ComponentDependency objects with same name and URL but different sub-paths: "
            + "None, foobar",
        ),
    ],
)
def test_component_dependency_update_error(
    d1: dict[str, str], d2: dict[str, str], expected_error: str
):
    d1 = _make_dep(
        d1["name"], d1.get("url", ""), instances=["cilium"], path=d1.get("path")
    )
    d2 = _make_dep(
        d2["name"], d2.get("url", ""), instances=["rook-ceph"], path=d2.get("path")
    )

    with pytest.raises(ValueError) as e:
        d1.update(d2)

    assert expected_error in str(e)


def test_component_dependency_error_helpers_single_instance():
    d = _make_dep(
        "argocd",
        "https://github.com/projectsyn/component-argocd.git",
        minverspec="v1.0.0",
    )
    assert (
        d.missing_dependency_error()
        == "Component instance 'test-component' requires dependency 'argocd' which isn't present in catalog"
    )
    assert (
        d.not_minversion_error("v0.8.1")
        == "Component instance 'test-component' requires dependency 'argocd' in a version '>= v1.0.0': "
        + "catalog has 'v0.8.1'"
    )


def test_component_dependency_error_helpers_multiple_instances():
    d = _make_dep(
        "argocd",
        "https://github.com/projectsyn/component-argocd.git",
        minverspec="v1.0.0",
        instances=["test-component-1", "test-component-2"],
    )
    assert (
        d.missing_dependency_error()
        == "Component instances 'test-component-1', 'test-component-2' require dependency 'argocd' "
        + "which isn't present in catalog"
    )
    assert (
        d.not_minversion_error("v0.8.1")
        == "Component instances 'test-component-1', 'test-component-2' require dependency 'argocd' "
        + "in a version '>= v1.0.0': catalog has 'v0.8.1'"
    )


def test_component_dependency_mandatory_required_for_catalog(config: Config):
    d = _make_dep(
        "argocd",
        "https://github.com/projectsyn/component-argocd.git",
    )
    assert d.required_for_catalog(config, {}, {})


@pytest.mark.parametrize(
    "requiredif,required",
    [
        (["facts.distribution=='openshift4'"], False),
        (["facts.distribution=='talos'"], True),
        (
            [
                "facts.distribution=='talos' && (config.foo=='bar' || config.param == 'temporary')"
            ],
            True,
        ),
    ],
)
def test_component_dependency_required_for_catalog(
    config: Config, requiredif: list[str], required: bool
):
    d = _make_dep(
        "argocd",
        "https://github.com/projectsyn/component-argocd.git",
        requiredif=requiredif,
    )

    facts = {
        "distribution": "talos",
    }
    cparams = {
        "foo": "bar",
        "param": "value",
    }

    assert d.required_for_catalog(config, cparams, facts) == required


@pytest.mark.parametrize(
    "requiredif,expected_error",
    [
        (
            ["facts.distribution"],
            "Component dependency `requiredif` CEL expression must evaluate to a boolean",
        ),
        (
            ["facts.cloud == 'cloudscale'"],
            'Evaluation failed for `requiredif` CEL expression: NOT_FOUND: Key not found in map : "cloud"\'',
        ),
    ],
)
def test_component_dependency_required_for_catalog_errors(
    config: Config, requiredif: list[str], expected_error: str
):
    d = _make_dep(
        "argocd",
        "https://github.com/projectsyn/component-argocd.git",
        requiredif=requiredif,
    )

    facts = {
        "distribution": "talos",
    }
    cparams = {
        "foo": "bar",
        "param": "value",
    }

    with pytest.raises(ValueError) as e:
        d.required_for_catalog(config, cparams, facts)

    assert expected_error in str(e)


@pytest.mark.parametrize(
    "dep,expected",
    [
        (
            _make_dep(
                "argocd",
                "https://github.com/projectsyn/component-argocd.git",
            ),
            {
                "url": "https://github.com/projectsyn/component-argocd.git",
                "version": "master",
            },
        ),
        (
            _make_dep(
                "argocd",
                "https://github.com/projectsyn/component-argocd.git",
                minverspec="v1.0.0",
            ),
            {
                "url": "https://github.com/projectsyn/component-argocd.git",
                "version": "v1.0.0",
            },
        ),
        (
            _make_dep(
                "argocd",
                "https://github.com/projectsyn/component-argocd.git",
                path="foobar",
            ),
            {
                "url": "https://github.com/projectsyn/component-argocd.git",
                "version": "master",
                "path": "foobar",
            },
        ),
    ],
)
def test_component_dependency_component_entry(dep, expected):
    assert dep.component_entry == expected


def _make_inv(config: Config, tmp_path: Path, inject_errors: bool = False):
    cluster = {
        "parameters": {
            # NOTE(sg): because we don't use fetch_components() in the tests, this isn't read
            # directly. Instead we directly read the version field below when we create the
            # `Component` objects.
            "components": {
                "test-component-1": {
                    "url": "https://github.com/projectsyn/component-tc1.git",
                    "version": "v1.0.1",
                },
                "test-component-2": {
                    "url": "https://github.com/projectsyn/component-tc2.git",
                    "version": "v1.0.2",
                },
                "test-component-3": {
                    "url": "https://github.com/projectsyn/component-tc3.git",
                    "version": "v1.0.3",
                },
                "test-component-4": {
                    "url": "https://github.com/projectsyn/component-tc4.git",
                    "version": "v1.0.4",
                },
                "test-component-5": {
                    "url": "https://github.com/projectsyn/component-tc5.git",
                    "version": "v1.0.0" if inject_errors else "v1.0.5",
                },
                "test-component-6": {
                    "url": "https://github.com/projectsyn/component-tc6.git",
                    "version": "feat/test",
                },
            },
            "facts": {
                "distribution": "talos",
                "cloud": "cloudscale",
            },
            "test_component_1": {},
            "test_component_2": {},
            "test_component_3": {
                "tc4_enabled": True,
            },
            "test_component_4": {},
            "test_component_5": {},
            "test_component_6": {},
        }
    }

    tc1 = copy.deepcopy(cluster)
    tc1["parameters"]["commodore"] = {
        "dependencies": {
            "test-component-2": {
                "url": "https://github.com/projectsyn/component-tc2.git",
            },
            "test-component-3": {
                "url": "https://github.com/projectsyn/component-tc2.git",
                "minversion": "v1.1.0",
                "requiredif": "facts.distribution == 'openshift4'",
            },
        }
    }
    tc2 = copy.deepcopy(cluster)
    if inject_errors:
        tc2["parameters"]["commodore"] = {
            "dependencies": {
                "fake-component-1": {
                    "url": "https://github.com/projectsyn/component-fc1.git",
                }
            }
        }
    tc3 = copy.deepcopy(cluster)
    tc3["parameters"]["commodore"] = {
        "dependencies": {
            "test-component-4": {
                "url": "https://github.com/projectsyn/component-tc4.git",
                "requiredif": "facts.distribution == 'talos' && config.tc4_enabled",
            },
        }
    }
    tc4 = copy.deepcopy(cluster)
    tc4["parameters"]["commodore"] = {
        "dependencies": {
            "test-component-5": {
                "url": "https://github.com/projectsyn/component-tc5.git",
                "minversion": "v1.0.1",
            }
        }
    }
    tc5 = copy.deepcopy(cluster)
    if inject_errors:
        tc5["parameters"]["commodore"] = {
            "dependencies": {
                "test-component-2": {
                    "url": "https://github.com/projectsyn/component-tc2.git",
                },
                "test-component-6": {
                    "url": "https://github.com/projectsyn/component-tc6.git",
                    "minversion": "v1.0.0",
                },
            }
        }
    tc6 = copy.deepcopy(cluster)

    inv = {
        "cluster": cluster,
        "test-component-1": tc1,
        "test-component-2": tc2,
        "test-component-3": tc3,
        "test-component-4": tc4,
        "test-component-5": tc5,
        "test-component-6": tc6,
    }
    for i in range(1, 7):
        cdep = MultiDependency(
            f"https://github.com/projectsyn/component-tc{i}.git",
            tmp_path / "dependencies",
        )
        c = Component(
            f"test-component-{i}",
            dependency=cdep,
            work_dir=tmp_path,
            version=cluster["parameters"]["components"][f"test-component-{i}"][
                "version"
            ],
        )
        config.register_component(c)
    config.register_component_aliases(
        {
            "test-component-1": "test-component-1",
            "test-component-2": "test-component-2",
            "test-component-3": "test-component-3",
            "test-component-4": "test-component-4",
            "test-component-5": "test-component-5",
            "test-component-6": "test-component-6",
        }
    )
    return inv


def test_collect_catalog_dependencies(tmp_path: Path, config: Config):
    inv = _make_inv(config, tmp_path)

    deps = component_dependency.collect_catalog_dependencies(config, inv)

    expected_deps = {
        "test-component-2": _make_dep(
            "test-component-2",
            "https://github.com/projectsyn/component-tc2.git",
            instances=["test-component-1"],
        ),
        "test-component-4": _make_dep(
            "test-component-4",
            "https://github.com/projectsyn/component-tc4.git",
            instances=["test-component-3"],
            requiredif=["facts.distribution == 'talos' && config.tc4_enabled"],
        ),
        "test-component-5": _make_dep(
            "test-component-5",
            "https://github.com/projectsyn/component-tc5.git",
            instances=["test-component-4"],
            minverspec="v1.0.1",
        ),
    }

    assert deps == expected_deps


def test_validate_catalog_dependencies(config: Config, tmp_path: Path):
    inv = _make_inv(config, tmp_path)
    component_dependency.validate_catalog_dependencies(config, inv)


def test_validate_catalog_dependencies_errors(config: Config, tmp_path: Path):
    inv = _make_inv(config, tmp_path, inject_errors=True)
    config.update_verbosity(3)

    with pytest.raises(click.ClickException) as e:
        component_dependency.validate_catalog_dependencies(config, inv)

    elines = e.value.message.split("\n")

    assert len(elines) == 3
    assert elines[0] == "catalog dependency validation failed:"
    assert (
        elines[1]
        == " * Component instance 'test-component-2' requires dependency 'fake-component-1' "
        + "which isn't present in catalog"
    )
    assert (
        elines[2]
        == " * Component instance 'test-component-4' requires dependency 'test-component-5' "
        + "in a version '>= v1.0.1': catalog has 'v1.0.0'"
    )
