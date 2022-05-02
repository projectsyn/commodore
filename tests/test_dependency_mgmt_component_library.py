from __future__ import annotations

import pytest

import click

from test_dependency_mgmt import setup_mock_component, data

from collections.abc import Iterable
from pathlib import Path
from typing import Optional

from commodore.config import Config
from commodore.inventory import Inventory

from commodore.dependency_mgmt import component_library


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
    libaliases: Optional[dict],
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

    component_library.create_component_library_aliases(data, cluster_params)

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
    tc1_libalias: dict[str, str],
    tc2_libalias: dict[str, str],
    tc3_libalias: dict[str, str],
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
            component_library.create_component_library_aliases(data, cluster_params)

        assert err in str(e.value)
