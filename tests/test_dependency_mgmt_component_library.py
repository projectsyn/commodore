from __future__ import annotations

import pytest

import click

from test_dependency_mgmt import setup_mock_component

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
    config: Config,
    libaliases: Optional[dict],
    expected_paths: Iterable[str],
    stdout: str,
):
    component = setup_mock_component(tmp_path)
    config.register_component(component)
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

    component_library.create_component_library_aliases(config, cluster_params)

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
    "tc1_meta,tc2_meta,tc3_meta,err",
    [
        ({}, {}, {}, None),
        (
            {"library_aliases": {"foo.libsonnet": "tc1.libjsonnet"}},
            {},
            {},
            None,
        ),
        (
            {},
            {"library_aliases": {"foo.libsonnet": "tc2.libjsonnet"}},
            {},
            None,
        ),
        (
            {"library_aliases": {"foo.libsonnet": "tc1.libjsonnet"}},
            {"library_aliases": {"foo.libsonnet": "tc2.libjsonnet"}},
            {},
            "Components 'tc1' and 'tc2' both define component library alias 'foo.libsonnet'",
        ),
        (
            {"library_aliases": {"foo.libsonnet": "tc1.libjsonnet"}},
            {"library_aliases": {"foo.libsonnet": "tc2.libjsonnet"}},
            {"library_aliases": {"foo.libsonnet": "tc3.libjsonnet"}},
            "Components 'tc1', 'tc2', and 'tc3' all define component library alias 'foo.libsonnet'",
        ),
        (
            {"library_aliases": {"tc2-fake.libsonnet": "tc1.libjsonnet"}},
            {},
            {},
            "Invalid alias prefix 'tc2' for template library alias of component 'tc1'",
        ),
        # NOTE: we don't test the informational messages printed out when additional
        # library prefixes are allowed or denied, we only test that there is an error
        # message or not.
        (
            {
                "library_aliases": {"tc2-fake.libsonnet": "tc1.libjsonnet"},
                "replaces": "tc2",
            },
            {"deprecated": True, "replaced_by": "tc1"},
            {},
            None,
        ),
        (
            {
                "library_aliases": {"tc2-fake.libsonnet": "tc1.libjsonnet"},
                "replaces": "tc2",
            },
            {"deprecated": True, "replaced_by": "tc3"},
            {},
            "Invalid alias prefix 'tc2' for template library alias of component 'tc1'",
        ),
        (
            {
                "library_aliases": {"tc2-fake.libsonnet": "tc1.libjsonnet"},
                "replaces": "tc2",
            },
            {"deprecated": False, "replaced_by": "tc2"},
            {},
            "Invalid alias prefix 'tc2' for template library alias of component 'tc1'",
        ),
    ],
)
def test_create_component_library_aliases_multiple_component(
    tmp_path: Path,
    config: Config,
    tc1_meta: dict[str, str],
    tc2_meta: dict[str, str],
    tc3_meta: dict[str, str],
    err: Optional[str],
):
    c1 = setup_mock_component(tmp_path, name="tc1")
    c2 = setup_mock_component(tmp_path, name="tc2")
    c3 = setup_mock_component(tmp_path, name="tc3")

    config.inventory.ensure_dirs()

    config.register_component(c1)
    config.register_component(c2)
    config.register_component(c3)

    cluster_params = {
        c1.parameters_key: {
            "_metadata": tc1_meta,
        },
        c2.parameters_key: {
            "_metadata": tc2_meta,
        },
        c3.parameters_key: {
            "_metadata": tc3_meta,
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
            component_library.create_component_library_aliases(config, cluster_params)

        assert err in str(e.value)

    else:
        component_library.create_component_library_aliases(config, cluster_params)
