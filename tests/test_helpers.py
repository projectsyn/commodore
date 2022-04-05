"""
Unit-tests for helpers
"""
import os
from pathlib import Path
from typing import Callable, Optional
import textwrap

import click
import pytest
import responses
from url_normalize import url_normalize

import commodore.helpers as helpers
from commodore.config import Config
from commodore.component import Component, component_dir


def test_apierror():
    e = helpers.ApiError("test")
    assert f"{e}" == "test"

    try:
        raise helpers.ApiError("test2")
    except helpers.ApiError as e2:
        assert f"{e2}" == "test2"


def test_clean_working_tree(tmp_path: Path):
    cfg = Config(work_dir=tmp_path)
    cfg.inventory.ensure_dirs()
    d = component_dir(tmp_path, "test")
    assert not d.is_dir()
    Component("test", work_dir=tmp_path)
    assert d.is_dir()
    helpers.clean_working_tree(cfg)
    assert d.is_dir()


def _test_yaml_dump_fun(
    dumpfunc: Callable[[str, Path], None], tmp_path: Path, input, expected
):
    output = tmp_path / "test.yaml"
    dumpfunc(input, output)
    with open(output) as f:
        data = "".join(f.readlines())
    assert expected == data


@pytest.mark.parametrize(
    "input,expected",
    [
        (
            {"a": 1, "b": "test"},
            textwrap.dedent(
                """
                a: 1
                b: test
                """
            )[1:],
        ),
        (
            {"a": [1, 2], "b": "test"},
            textwrap.dedent(
                """
                a:
                - 1
                - 2
                b: test
                """
            )[1:],
        ),
        (
            {"a": {"test": 1}, "b": "test"},
            textwrap.dedent(
                """
                a:
                  test: 1
                b: test
                """
            )[1:],
        ),
        (
            {"a": "first line\nsecond line", "b": "test"},
            textwrap.dedent(
                """
                a: |-
                  first line
                  second line
                b: test
                """
            )[1:],
        ),
    ],
)
def test_yaml_dump(tmp_path: Path, input, expected):
    _test_yaml_dump_fun(helpers.yaml_dump, tmp_path, input, expected)


@pytest.mark.parametrize(
    "input,expected",
    [
        (
            [{"a": 1}, {"b": "test"}],
            textwrap.dedent(
                """
                    a: 1
                    ---
                    b: test
                    """
            )[1:],
        ),
        (
            [{"a": {"test": "first line\nsecond line"}}, {"b": "test"}],
            textwrap.dedent(
                """
                a:
                  test: |-
                    first line
                    second line
                ---
                b: test
                """
            )[1:],
        ),
        (
            [{"a": [1, 2]}, {"b": "test"}],
            textwrap.dedent(
                """
                a:
                - 1
                - 2
                ---
                b: test
                """
            )[1:],
        ),
    ],
)
def test_yaml_dump_all(tmp_path: Path, input, expected):
    _test_yaml_dump_fun(helpers.yaml_dump_all, tmp_path, input, expected)


@pytest.mark.parametrize(
    "sequence,winsize,expected",
    [
        (
            "abcd",
            1,
            [("a",), ("b",), ("c",), ("d",)],
        ),
        (
            "abcd",
            2,
            [("a", "b"), ("b", "c"), ("c", "d")],
        ),
        (
            "abcd",
            4,
            [("a", "b", "c", "d")],
        ),
        (
            ["aaa", "bbb", "ccc", "ddd"],
            2,
            [("aaa", "bbb"), ("bbb", "ccc"), ("ccc", "ddd")],
        ),
    ],
)
def test_sliding_window(sequence, winsize, expected):
    windows = list(helpers.sliding_window(sequence, winsize))
    assert windows == expected


def _verify_call_status(query_url):
    assert len(responses.calls) == 1
    call = responses.calls[0]
    assert "Authorization" in call.request.headers
    assert call.request.headers["Authorization"] == "Bearer token"
    assert call.request.url == query_url


@responses.activate
def test_lieutenant_query_connection_error():
    api_url = "https://syn.example.com"
    with pytest.raises(
        helpers.ApiError, match=f"Unable to connect to Lieutenant at {api_url}"
    ):
        helpers.lieutenant_query(api_url, "token", "clusters", "c-cluster-id-1234")

    _verify_call_status(f"{api_url}/clusters/c-cluster-id-1234")


@pytest.mark.parametrize(
    "response,expected",
    [
        (
            {
                "status": 403,
                "json": {"reason": "Unauthorized"},
            },
            "API returned 403: Unauthorized",
        ),
        (
            {
                "status": 403,
                "json": {},
            },
            "API returned 403: ",
        ),
        (
            {
                "status": 500,
                "json": {"reason": "Unexpected frobulation"},
            },
            "API returned 500: Unexpected frobulation",
        ),
        (
            {
                "status": 200,
                "body": "No JSON in response",
            },
            "Client error: Unable to parse JSON",
        ),
        (
            {
                "status": 403,
                "body": "No JSON in response",
            },
            "Client error: Unable to parse JSON",
        ),
    ],
)
@responses.activate
def test_lieutenant_query_response_errors(response, expected):
    base_url = "https://syn.example.com/"

    query_url = url_normalize(f"{base_url}/clusters/")

    if "json" in response:
        responses.add(
            responses.GET,
            query_url,
            status=response["status"],
            json=response["json"],
        )
    elif "body" in response:
        responses.add(
            responses.GET,
            query_url,
            status=response["status"],
            body=response["body"],
        )

    with pytest.raises(helpers.ApiError, match=expected):
        helpers.lieutenant_query(base_url, "token", "clusters", "")

    _verify_call_status(query_url)


def test_relsymlink(tmp_path: Path):
    test_file = tmp_path / "src" / "test"
    test_file.parent.mkdir(parents=True, exist_ok=True)
    with open(test_file, "w") as f:
        f.write("test")

    helpers.relsymlink(test_file, tmp_path)
    assert (tmp_path / "test").is_symlink()
    assert (tmp_path / "test").exists()
    with open(tmp_path / "test") as f:
        assert f.read() == "test"


def test_override_relsymlink(tmp_path: Path):
    test_file = tmp_path / "src" / "test2"
    test_file.parent.mkdir()
    test_file.touch()
    helpers.relsymlink(test_file, tmp_path)
    assert (tmp_path / "test2").is_symlink()


@pytest.mark.parametrize("dst_is_dangling", [None, True, False])
def test_relsymlink_dest_name(tmp_path: Path, dst_is_dangling: Optional[bool]):
    src = tmp_path / "src.txt"
    dst = tmp_path / "dst.txt"

    with open(src, "w") as f:
        f.write("Test")

    if dst_is_dangling is not None:
        if dst_is_dangling:
            os.symlink(tmp_path / "err.txt", dst)
        else:
            os.symlink(tmp_path / "src.txt", dst)

    helpers.relsymlink(src, tmp_path, dest_name="dst.txt")


def test_relsymlink_invalid_src_exception(tmp_path: Path):
    src = tmp_path / "src.txt"

    with pytest.raises(click.ClickException) as e:
        helpers.relsymlink(src, tmp_path, dest_name="dst.txt")

    print(str(e.value))
    assert (
        f"Can't link {src.name} to {tmp_path / 'dst.txt'}. Source does not exist."
        in str(e.value)
    )
