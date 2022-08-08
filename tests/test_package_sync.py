from __future__ import annotations

import json

from pathlib import Path

import click
import git
import github
import pytest
import responses

from test_package import _setup_package_remote

from commodore.config import Config
from commodore.package import Package
from commodore.package import sync

DATA_DIR = Path(__file__).parent.absolute() / "testdata" / "github"


@pytest.mark.parametrize("sync_branch", ["none", "local", "remote"])
def test_ensure_branch(tmp_path: Path, config: Config, sync_branch: str):
    _setup_package_remote("foo", tmp_path / "foo.git")
    if sync_branch == "remote":
        r = git.Repo(tmp_path / "foo.git")
        r.create_head("template-sync")
    p = Package.clone(config, f"file://{tmp_path}/foo.git", "foo")
    if sync_branch == "local":
        orig_head = p.repo.repo.head
        p.repo.repo.create_head("template-sync")

        p.checkout()
        assert p.repo.repo.head == orig_head

    with open(p.target_dir / "test.txt", "w", encoding="utf-8") as f:
        f.write("Hello, world\n")
    p.repo.commit("Add test.txt")

    r = p.repo.repo

    assert any(h.name == "template-sync" for h in r.heads) == (sync_branch == "local")

    sync.ensure_branch(p)

    hs = [h for h in r.heads if h.name == "template-sync"]
    assert len(hs) == 1

    h = hs[0]
    assert h.commit.message == "Add test.txt"


API_TOKEN_MATCHER = responses.matchers.header_matcher(
    {"Authorization": "token ghp_fake-token"}
)


def _setup_gh_get_responses(has_open_pr: bool):

    with open(DATA_DIR / "projectsyn-package-foo-response.json", encoding="utf-8") as f:
        resp = json.load(f)
        responses.add(
            responses.GET,
            "https://api.github.com:443/repos/projectsyn/package-foo",
            status=200,
            json=resp,
            match=[API_TOKEN_MATCHER],
        )

    if has_open_pr:
        with open(
            DATA_DIR / "projectsyn-package-foo-response-pulls.json", encoding="utf-8"
        ) as f:
            pulls = json.load(f)
    else:
        pulls = []
    responses.add(
        responses.GET,
        "https://api.github.com:443/repos/projectsyn/package-foo/pulls",
        json=pulls,
        status=200,
        match=[API_TOKEN_MATCHER],
    )


def labels_post_body_match(request) -> tuple[bool, str]:
    """Custom matcher for the labels API POST request body.

    `responses.matchers.json_params_matcher()` doesn't support top-level JSON
    list, but PyGitHub just posts a top-level list when updating labels, so we
    implement our own matcher function."""
    reason = ""
    request_body = request.body
    try:
        if isinstance(request_body, bytes):
            request_body = request_body.decode("utf-8")
        json_body = json.loads(request_body) if request_body else []

        valid = json_body == ["template-sync"]

        if not valid:
            reason = "request.body doesn't match: {} doesn't match {}".format(
                json_body, ["template-sync"]
            )

    except json.JSONDecodeError:
        valid = False
        reason = (
            "request.body doesn't match: JSONDecodeError: Cannot parse request.body"
        )

    return valid, reason


def _setup_gh_pr_response(method):
    with open(
        DATA_DIR / "projectsyn-package-foo-response-pr.json", encoding="utf-8"
    ) as f:
        resp = json.load(f)
        suffix = ""
        body_matcher = responses.matchers.json_params_matcher(
            {
                "title": "Update from package template",
                "body": "",
                "draft": False,
                "base": "master",
                "head": "template-sync",
            }
        )
        if method == responses.PATCH:
            suffix = "/1"
            body_matcher = responses.matchers.json_params_matcher({"body": ""})
        responses.add(
            method,
            f"https://api.github.com:443/repos/projectsyn/package-foo/pulls{suffix}",
            json=resp,
            status=200,
            match=[API_TOKEN_MATCHER, body_matcher],
        )

    if method == responses.POST:
        label_resp = [
            {
                "id": 4405096203,
                "node_id": "LA_kwDOHyQSds8AAAABBpBvCw",
                "url": "https://api.github.com/repos/projectsyn/package-foo/labels/template-sync",
                "name": "template-sync",
                "color": "ededed",
                "default": False,
                "description": None,
            }
        ]

        responses.add(
            responses.POST,
            "https://api.github.com:443/repos/projectsyn/package-foo/issues/1/labels",
            json=label_resp,
            status=200,
            match=[API_TOKEN_MATCHER, labels_post_body_match],
        )


@responses.activate
@pytest.mark.parametrize("dry_run", [True, False])
@pytest.mark.parametrize("pr_exists", [True, False])
def test_ensure_pr(
    capsys, tmp_path: Path, config: Config, dry_run: bool, pr_exists: bool
):
    _setup_gh_get_responses(pr_exists)
    if not dry_run:
        _setup_gh_pr_response(responses.PATCH if pr_exists else responses.POST)
    _setup_package_remote("foo", tmp_path / "foo.git")
    config.github_token = "ghp_fake-token"
    p = Package.clone(config, f"file://{tmp_path}/foo.git", "foo")
    pname = "projectsyn/package-foo"
    sync.ensure_branch(p)

    gh = github.Github(config.github_token)
    gr = gh.get_repo(pname)

    sync.ensure_pr(p, pname, gr, dry_run)

    if dry_run:
        captured = capsys.readouterr()
        cu = "update" if pr_exists else "create"
        assert f"Would {cu} PR for {pname}" in captured.out
        assert len(responses.calls) == 2
    else:
        assert len(responses.calls) == 3 + (1 if not pr_exists else 0)


@pytest.mark.parametrize(
    "ghtoken,package_list_contents",
    [
        (None, ""),
        ("ghp_token", '"foo"'),
        ("ghp_token", 'foo: "bar"'),
        ("ghp_token", "foo: bar:"),
        ("ghp_token", "fff: bar\n- foo"),
    ],
)
def test_sync_packages_package_list_parsing(
    tmp_path: Path, config: Config, ghtoken, package_list_contents
):
    config.github_token = ghtoken
    pkg_list = tmp_path / "pkgs.yaml"
    with open(pkg_list, "w", encoding="utf-8") as f:
        f.write(package_list_contents)

    with pytest.raises(click.ClickException) as exc:
        sync.sync_packages(config, pkg_list, False)

    if ghtoken is None:
        assert str(exc.value) == "Can't continue, missing GitHub API token."
    elif package_list_contents.endswith(":") or package_list_contents.startswith("fff"):
        # parse error
        assert str(exc.value) == f"Failed to parse YAML in '{pkg_list}'"
    else:
        # type error
        typ = "<class 'dict'>" if ":" in package_list_contents else "<class 'str'>"
        assert (
            str(exc.value)
            == f"Expected a list in '{pkg_list}', but got unexpected type: {typ}"
        )
