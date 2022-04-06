import os

from pathlib import Path
from typing import Any, Dict

import pytest

from commodore.config import Config
from commodore.helpers import yaml_dump, yaml_dump_all
from commodore.inventory import lint_components


@pytest.fixture
def config(tmp_path: Path):
    return Config(
        tmp_path,
        api_url="https://syn.example.com",
        api_token="token",
    )


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
]
SKIP_FILECONTENTS = [
    ("", "> Skipping empty file"),
    ("\tTest", "Unable to load as YAML"),
    ([{"a": 1}, {"b": 2}], "Linting multi-document YAML streams is not supported"),
    ([[1, 2, 3]], "Expected top-level dictionary in YAML document"),
]


def _check_lint_result(ec: int, expected_errcount: int, captured):
    assert ec == expected_errcount
    if ec == 0:
        assert captured.out == ""
    else:
        assert len(captured.out.strip().split("\n")) == expected_errcount


@pytest.mark.parametrize("filecontents,expected_errcount", LINT_FILECONTENTS)
def test_lint_component_versions(
    tmp_path, capsys, filecontents: Dict, expected_errcount: int
):
    p = tmp_path / "test.yml"

    ec = lint_components._lint_component_versions(p, filecontents)

    captured = capsys.readouterr()
    _check_lint_result(ec, expected_errcount, captured)


@pytest.mark.parametrize("filecontents,expected_errcount", LINT_FILECONTENTS)
def test_lint_valid_file(
    tmp_path: Path, capsys, config: Config, filecontents: Dict, expected_errcount: int
):
    testf = tmp_path / "test.yml"
    yaml_dump(filecontents, testf)

    ec = lint_components.lint_components(config, testf)

    captured = capsys.readouterr()
    _check_lint_result(ec, expected_errcount, captured)


@pytest.mark.parametrize("filecontents,expected_errcount", LINT_FILECONTENTS)
def test_lint_valid_file_stream(
    tmp_path: Path, capsys, config: Config, filecontents: Dict, expected_errcount: int
):
    testf = tmp_path / "test.yml"
    yaml_dump_all([filecontents], testf)

    ec = lint_components.lint_components(config, testf)

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

    ec = lint_components.lint_components(config, testf)

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
    ]
    assert len(lint_direntries) == len(LINT_FILECONTENTS)
    skip_direntries = [
        tmp_path / "empty.txt",
        tmp_path / "d3" / "tab.txt",
        tmp_path / "d3" / "stream.yaml",
        tmp_path / "d3" / "top-level.yaml",
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

    ec = lint_components.lint_components(config, tmp_path)

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

    ec = lint_components.lint_components(config, testf)

    captured = capsys.readouterr()
    _check_lint_result(ec, expected_errcount, captured)


def test_lint_components_directory(tmp_path: Path, config: Config, capsys):
    expected_errcount = _setup_directory(tmp_path)

    ec = lint_components.lint_components(config, tmp_path)

    captured = capsys.readouterr()
    _check_lint_result(ec, expected_errcount, captured)
