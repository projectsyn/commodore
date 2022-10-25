from __future__ import annotations

import os

from pathlib import Path
from typing import Any

import pytest

from commodore.config import Config
from commodore.helpers import yaml_dump, yaml_dump_all
from commodore.inventory import lint_dependency_specification
from commodore.inventory import lint


LINT_FILECONTENTS = [
    ({}, 0),
    ({"a": "b"}, 0),
    (
        {
            "parameters": {
                "components": {
                    "c1": {
                        "url": "https://example.com/syn/component-c1.git",
                        "version": "v1.0.0",
                    },
                    "c2": {
                        "url": "https://example.com/syn/component-c2.git",
                        "version": "v1.0.0",
                    },
                    "c3": {
                        "url": "https://example.com/syn/component-c3.git",
                        "version": "v1.0.0",
                        "path": "subpath",
                    },
                },
            }
        },
        0,
    ),
    (
        {
            "parameters": {
                "components": {
                    "c1": {
                        "url": "https://example.com/syn/component-c1.git",
                    },
                    "c2": {
                        "url": "https://example.com/syn/component-c2.git",
                        "version": "v1.0.0",
                    },
                    "c3": {
                        "url": "https://example.com/syn/component-c3.git",
                        "version": "v1.0.0",
                    },
                },
            }
        },
        1,
    ),
    (
        {
            "parameters": {
                "components": {
                    "c1": {
                        "url": "https://example.com/syn/component-c1.git",
                    },
                    "c2": {
                        "url": "https://example.com/syn/component-c2.git",
                    },
                    "c3": {
                        "version": "v1.0.0",
                    },
                },
            }
        },
        2,
    ),
    (
        {
            "parameters": {
                "components": {
                    "c1": {
                        "url": ["https://example.com/syn/component-c1.git"],
                        "version": "v1.0.0",
                        "vesrion": "v1.0.1",
                    },
                    "c2": {
                        "url": "https://example.com/syn/component-c2.git",
                        "version": 1.0,
                    },
                    "c3": {
                        "version": "v1.0.0",
                    },
                },
            }
        },
        3,
    ),
]
SKIP_FILECONTENTS = [
    ("", "> Skipping empty file"),
    ("\tTest", "Unable to load as YAML"),
    ([{"a": 1}, {"b": 2}], "Linting multi-document YAML streams is not supported"),
    ([[1, 2, 3]], "Expected top-level dictionary in YAML document"),
    ([{"parameters": ["foo", "bar"]}], "Expected key 'parameters' to be a dict"),
]


def _check_lint_result(ec: int, expected_errcount: int, captured):
    assert ec == expected_errcount
    if ec == 0:
        assert captured.out == ""
    else:
        assert len(captured.out.strip().split("\n")) == expected_errcount


@pytest.mark.parametrize("filecontents,expected_errcount", LINT_FILECONTENTS)
def test_lint_component_versions(
    tmp_path, capsys, filecontents: dict, expected_errcount: int
):
    p = tmp_path / "test.yml"

    ec = lint_dependency_specification.lint_components(p, filecontents)

    captured = capsys.readouterr()
    _check_lint_result(ec, expected_errcount, captured)


@pytest.mark.parametrize("filecontents,expected_errcount", LINT_FILECONTENTS)
def test_lint_valid_file(
    tmp_path: Path, capsys, config: Config, filecontents: dict, expected_errcount: int
):
    testf = tmp_path / "test.yml"
    yaml_dump(filecontents, testf)

    ec = lint.ComponentSpecLinter()(config, testf)

    captured = capsys.readouterr()
    _check_lint_result(ec, expected_errcount, captured)


@pytest.mark.parametrize("filecontents,expected_errcount", LINT_FILECONTENTS)
def test_lint_valid_file_stream(
    tmp_path: Path, capsys, config: Config, filecontents: dict, expected_errcount: int
):
    testf = tmp_path / "test.yml"
    yaml_dump_all([filecontents], testf)

    ec = lint.ComponentSpecLinter()(config, testf)

    captured = capsys.readouterr()
    _check_lint_result(ec, expected_errcount, captured)


def _dump_skip_file(filecontents: Any, path: Path):
    if isinstance(filecontents, str):
        with open(path, "w", encoding="utf-8") as t:
            t.write(filecontents)
    else:
        yaml_dump_all(filecontents, path)


@pytest.mark.parametrize("filecontents,expected_debug_msg", SKIP_FILECONTENTS)
def test_lint_skip_file(
    tmp_path: Path,
    capsys,
    config: Config,
    filecontents: Any,
    expected_debug_msg: str,
):
    # Enable debug verbosity
    config.update_verbosity(3)

    testf = tmp_path / "test.yml"
    _dump_skip_file(filecontents, testf)

    ec = lint.ComponentSpecLinter()(config, testf)

    captured = capsys.readouterr()
    stdout: str = captured.out

    assert ec == 0
    assert stdout.startswith(
        (f"> Skipping empty file {testf}", f"> Skipping file {testf}: ")
    )
    assert expected_debug_msg in captured.out


def _setup_directory(tmp_path: Path):
    lint_direntries = [
        tmp_path / "test.yml",
        tmp_path / "d1" / "test1.yml",
        tmp_path / "d1" / "test2.yml",
        tmp_path / "d2" / "test3.yml",
        tmp_path / "d2" / "subd" / "test4.yml",
        tmp_path / "d3" / "test5.yml",
    ]
    assert len(lint_direntries) == len(LINT_FILECONTENTS)
    skip_direntries = [
        tmp_path / "empty.txt",
        tmp_path / "d3" / "tab.txt",
        tmp_path / "d3" / "stream.yaml",
        tmp_path / "d3" / "top-level.yaml",
        tmp_path / "test6.yml",
    ]
    assert len(skip_direntries) == len(SKIP_FILECONTENTS)

    expected_errcount = 0
    for (idx, (filecontents, eec)) in enumerate(LINT_FILECONTENTS):
        dentry = lint_direntries[idx]
        os.makedirs(dentry.parent, exist_ok=True)
        yaml_dump(filecontents, dentry)
        # these should be skipped
        yaml_dump(filecontents, tmp_path / f".{idx}.yml")
        expected_errcount += eec
    for (idx, (filecontents, _)) in enumerate(SKIP_FILECONTENTS):
        dentry = skip_direntries[idx]
        os.makedirs(dentry.parent, exist_ok=True)
        _dump_skip_file(filecontents, dentry)

    return expected_errcount


def test_lint_directory(tmp_path: Path, capsys, config: Config):
    expected_errcount = _setup_directory(tmp_path)

    ec = lint.ComponentSpecLinter()(config, tmp_path)

    captured = capsys.readouterr()
    _check_lint_result(ec, expected_errcount, captured)


def test_lint_components_file(tmp_path: Path, config: Config, capsys):
    filecontents = {
        "parameters": {
            "components": {
                "c1": {
                    "url": "https://example.com/syn/component-c1.git",
                },
                "c2": {
                    "url": "https://example.com/syn/component-c2.git",
                },
                "c3": {
                    "version": "v1.0.0",
                },
            },
        }
    }
    expected_errcount = 2
    testf = tmp_path / "test.yml"
    yaml_dump(filecontents, testf)

    ec = lint.ComponentSpecLinter()(config, testf)

    captured = capsys.readouterr()
    _check_lint_result(ec, expected_errcount, captured)


def test_lint_components_directory(tmp_path: Path, config: Config, capsys):
    expected_errcount = _setup_directory(tmp_path)

    ec = lint.ComponentSpecLinter()(config, tmp_path)

    captured = capsys.readouterr()
    _check_lint_result(ec, expected_errcount, captured)


@pytest.mark.parametrize(
    "ignore_patterns,file_paths,expected_errcount",
    [
        (("test.yml",), ["test.yml"], 0),
        (("test.yml",), ["test.yml", "a/test.yml"], 0),
        (("test.yml",), ["test.yml", "a/b/c/test.yml"], 0),
        (("/test.yml",), ["test.yml", "a/test.yml"], 2),  # shouldn't match `a/test.yml`
        (("/*.yml",), ["test.yml", "foo.yml"], 0),
        (("/*.yml",), ["test.yml", "foo.yaml"], 2),  # shouldn't match `foo.yaml`
        (
            ("/tes?.yml",),
            ["test.yml", "tesu.yml", "fest.yml"],
            2,
        ),  # shouldn't match `fest.yml`
        (("[t-z]*",), ["test.yml", "uuu"], 0),
        (("[t-z]*",), ["test.yml", "uuu", "fest.yml"], 2),  # shouldn't match `fest.yml`
        (
            ("/manifests",),
            ["test.yml", "manifests/foo.yml", "manifests/bar.yml"],
            2,
        ),  # shouldn't match anything under `/manifests`
        (
            (
                "test.yml",
                "/manifests",
            ),
            ["test.yml", "manifests/foo.yml", "manifests/bar.yml"],
            0,
        ),  # shouldn't match anything
    ],
)
def test_lint_components_ignored_path(
    tmp_path: Path,
    config: Config,
    capsys,
    ignore_patterns: tuple[str],
    file_paths: list[str],
    expected_errcount: int,
):
    """Each file gets the same contents which should cause 2 errors unless the file is
    ignored."""
    filecontents = {
        "parameters": {
            "components": {
                "c1": {
                    "url": "https://example.com/syn/component-c1.git",
                },
                "c2": {
                    "url": "https://example.com/syn/component-c2.git",
                },
                "c3": {
                    "version": "v1.0.0",
                },
            },
        }
    }
    for f in file_paths:
        testf = tmp_path / f
        testf.parent.mkdir(parents=True, exist_ok=True)
        yaml_dump(filecontents, testf)

    ec = lint.ComponentSpecLinter()(config, tmp_path, ignore_patterns)

    captured = capsys.readouterr()
    _check_lint_result(ec, expected_errcount, captured)
