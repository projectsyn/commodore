from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from commodore.config import Config
from commodore.inventory import lint_deprecated_parameters, lint


@pytest.fixture
def config(tmp_path: Path):
    return Config(
        tmp_path,
        api_url="https://syn.example.com",
        api_token="token",
    )


@pytest.mark.parametrize(
    "data,expected",
    [
        ({}, ""),
        ({"key": ""}, ""),
        ({"key": "${some:ref}"}, ""),
        (
            {"key": "${customer:name}"},
            "> Field 'key' in file 'test.yaml' contains deprecated parameter '${customer:name}'\n",
        ),
        (
            {"key": "${some:${customer:name}}"},
            "> Field 'key' in file 'test.yaml' contains deprecated parameter '${customer:name}'\n",
        ),
        (
            {"key": "embedded-${customer:name}"},
            "> Field 'key' in file 'test.yaml' contains deprecated parameter '${customer:name}'\n",
        ),
        (
            {"key": "${cluster:dist}"},
            "> Field 'key' in file 'test.yaml' contains deprecated parameter '${cluster:dist}'\n",
        ),
        (
            {"key": "${cloud:provider}"},
            "> Field 'key' in file 'test.yaml' contains deprecated parameter '${cloud:provider}'\n",
        ),
        (
            {"key": "${cloud:region}"},
            "> Field 'key' in file 'test.yaml' contains deprecated parameter '${cloud:region}'\n",
        ),
        ({"list": [1, 2, 3]}, ""),
        (
            {"list": ["test", "${customer:name}", "aaa"]},
            "Field 'list[1]' in file 'test.yaml' contains deprecated parameter '${customer:name}'\n",
        ),
        (
            {"list": ["test", {"name": "${customer:name}"}, "aaa"]},
            "Field 'list[1].name' in file 'test.yaml' contains deprecated parameter '${customer:name}'\n",
        ),
        (
            {"list": ["test", {"name": "${customer:name}"}, "${customer:name}"]},
            "> Field 'list[1].name' in file 'test.yaml' contains deprecated parameter '${customer:name}'\n"
            + "> Field 'list[2]' in file 'test.yaml' contains deprecated parameter '${customer:name}'\n",
        ),
        (
            {"nested": {"key": "${customer:name}"}},
            "> Field 'nested.key' in file 'test.yaml' contains deprecated parameter '${customer:name}'\n",
        ),
        (
            {
                "unlintable:int": 1,
                "unlintable:float": 1.0,
                "unlintable:bool": True,
                "key": "${customer:name}",
            },
            "> Field 'key' in file 'test.yaml' contains deprecated parameter '${customer:name}'",
        ),
    ],
)
def test_lint_deprecated_parameters(capsys, data: dict[str, Any], expected: str):
    file = Path("test.yaml")

    ec = lint_deprecated_parameters.lint_deprecated_parameters(file, data)

    captured = capsys.readouterr()
    assert expected in captured.out
    expected_count = len(expected.strip().split("\n")) if len(expected) > 0 else 0
    assert ec == expected_count


def test_lint_deprecated_parameters_directory(capsys, tmp_path: Path, config: Config):
    with open(tmp_path / "test.yaml", "w") as f:
        yaml.safe_dump(
            {
                "list": ["test", {"name": "${customer:name}"}, "${customer:name}"],
                "unlintable:int": 1,
                "unlintable:float": 1.0,
                "unlintable:bool": True,
                "key": "${customer:name}",
            },
            f,
        )

    ec = lint.DeprecatedParameterLinter()(config, tmp_path)

    captured = capsys.readouterr()
    out_lines = captured.out.strip().split("\n")

    assert ec == 3
    assert len(out_lines) == 3
    assert (
        f"> Field 'key' in file '{tmp_path/'test.yaml'}' contains deprecated parameter '${{customer:name}}'"
        in out_lines
    )
    assert (
        f"> Field 'list[1].name' in file '{tmp_path/'test.yaml'}' contains deprecated parameter '${{customer:name}}'"
        in out_lines
    )
    assert (
        f"> Field 'list[2]' in file '{tmp_path/'test.yaml'}' contains deprecated parameter '${{customer:name}}'"
        in out_lines
    )
