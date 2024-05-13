"""
Tests for catalog internals
"""

from __future__ import annotations

import os
import copy
from pathlib import Path
from unittest.mock import patch

import click
import git
import pytest
import responses
import yaml
import textwrap

from commodore import catalog
from commodore.config import Config
from commodore.cluster import Cluster

cluster_resp = {
    "id": "c-test",
    "tenant": "t-test",
    "displayName": "test-cluster",
    "facts": {
        "cloud": "local",
        "distribution": "k3s",
    },
    "gitRepo": {
        "url": "ssh://git@github.com/projectsyn/test-cluster-catalog.git",
    },
}

tenant_resp = {
    "id": "t-test",
    "displayName": "Test tenant",
    "gitRepo": {
        "url": "https://github.com/projectsyn/test-tenant.git",
    },
    "globalGitRepoURL": "https://github.com/projectsyn/commodore-defaults.git",
    "globalGitRepoRevision": "v0.12.0",
}


def make_cluster_resp(
    id: str, displayName: str = "Test cluster", tenant: str = "t-test-tenant"
) -> dict:
    r = copy.deepcopy(cluster_resp)
    r["id"] = id
    r["displayName"] = displayName
    r["tenant"] = tenant

    return r


@pytest.fixture
def cluster() -> Cluster:
    return Cluster(
        cluster_resp,
        tenant_resp,
    )


@pytest.fixture
def inexistent_cluster() -> Cluster:
    cr = copy.deepcopy(cluster_resp)
    cr["gitRepo"]["url"] = "https://git.example.org/cluster-catalog.git"
    return Cluster(
        cr,
        tenant_resp,
    )


@pytest.fixture
def fresh_cluster(tmp_path: Path) -> Cluster:
    cr = copy.deepcopy(cluster_resp)

    git.Repo.init(tmp_path / "repo.git", bare=True)

    cr["gitRepo"]["url"] = f"file:///{tmp_path}/repo.git"
    return Cluster(
        cr,
        tenant_resp,
    )


def test_catalog_commit_message(tmp_path: Path):
    config = Config(
        tmp_path,
        api_url="https://syn.example.com",
        api_token="token",
    )

    commit_message = catalog._render_catalog_commit_msg(config)
    assert not commit_message.startswith("\n")
    assert commit_message.startswith("Automated catalog update from Commodore\n\n")


def test_fetch_catalog_inexistent(
    tmp_path: Path, config: Config, inexistent_cluster: Cluster
):
    with pytest.raises(Exception) as e:
        catalog.fetch_catalog(config, inexistent_cluster)

    assert inexistent_cluster.catalog_repo_url in str(e.value)


def test_fetch_catalog_initial_commit_for_empty_repo(
    tmp_path: Path, config: Config, fresh_cluster: Cluster
):
    r = catalog.fetch_catalog(config, fresh_cluster)

    assert r.repo.head
    assert r.working_tree_dir
    assert r.repo.head.commit.message == "Initial commit"


def setup_catalog_for_push(config: Config, cluster: Cluster):
    repo = catalog.fetch_catalog(config, cluster)
    with open(repo.working_tree_dir / "test.txt", "w") as f:
        f.writelines(["foo"])

    repo.stage_files(["test.txt"])

    return repo


@pytest.mark.parametrize("push", [True, False])
@pytest.mark.parametrize("local", [True, False])
def test_push_catalog(
    capsys,
    tmp_path: Path,
    config: Config,
    fresh_cluster: Cluster,
    push: bool,
    local: bool,
):
    repo = setup_catalog_for_push(config, fresh_cluster)

    config.push = push
    config.local = local

    catalog._push_catalog(config, repo, "Add test.txt")

    upstream = git.Repo(tmp_path / "repo.git")
    captured = capsys.readouterr()

    if local:
        assert len(upstream.branches) == 0
        assert repo.repo.untracked_files == ["test.txt"]
        assert not repo.repo.is_dirty()
        assert "Skipping commit+push to catalog in local mode..." in captured.out
    elif push:
        assert upstream.active_branch.commit.message == "Add test.txt"
        assert repo.repo.untracked_files == []
        assert not repo.repo.is_dirty()
        assert "Commiting changes..." in captured.out
        assert "Pushing catalog to remote..." in captured.out
    else:
        assert len(upstream.branches) == 0
        assert repo.repo.untracked_files == []
        assert repo.repo.is_dirty()
        assert ("test.txt", 0) in repo.repo.index.entries
        assert "Skipping commit+push to catalog..." in captured.out


@pytest.mark.parametrize("interactive", ["y", "n"])
@patch("click.confirm")
def test_push_catalog_interactive(
    mock_confirm,
    capsys,
    tmp_path: Path,
    config: Config,
    fresh_cluster: Cluster,
    interactive: str,
):
    repo = setup_catalog_for_push(config, fresh_cluster)

    config.push = True
    config.interactive = True
    mock_confirm.return_value = interactive == "y"

    catalog._push_catalog(config, repo, "Add test.txt")

    upstream = git.Repo(tmp_path / "repo.git")
    captured = capsys.readouterr()

    if interactive == "y":
        assert upstream.active_branch.commit.message == "Add test.txt"
        assert repo.repo.untracked_files == []
        assert not repo.repo.is_dirty()
        assert "Commiting changes..." in captured.out
        assert "Pushing catalog to remote..." in captured.out
    else:
        assert len(upstream.branches) == 0
        assert repo.repo.untracked_files == []
        assert repo.repo.is_dirty()
        assert ("test.txt", 0) in repo.repo.index.entries
        assert "Skipping commit+push to catalog..." in captured.out


def test_push_catalog_giterror(config: Config, fresh_cluster: Cluster):
    repo = setup_catalog_for_push(config, fresh_cluster)

    config.push = True
    repo.remote = "file:///path/to/repo.git"

    with pytest.raises(click.ClickException) as e:
        catalog._push_catalog(config, repo, "Add test.txt")

    assert (
        "Failed to push to the catalog repository: Git exited with status code"
        in str(e)
    )


def test_push_catalog_remoteerror(
    tmp_path: Path, config: Config, fresh_cluster: Cluster
):
    repo = setup_catalog_for_push(config, fresh_cluster)

    config.push = True
    hook_path = tmp_path / "repo.git" / "hooks" / "pre-receive"
    with open(hook_path, "w") as hookf:
        hookf.write("#!/bin/sh\necho 'Push denied'\nexit 1")

    hook_path.chmod(0o755)

    with pytest.raises(click.ClickException) as e:
        catalog._push_catalog(config, repo, "Add test.txt")

    assert (
        "Failed to push to the catalog repository: [remote rejected] (pre-receive hook declined)"
        in str(e)
    )


def write_target_file_1(target: Path, name="test.txt"):
    with open(target / name, "w") as f:
        yaml.safe_dump_all(
            [
                None,
                {
                    "kind": "test1",
                    "metadata": {"namespace": "test"},
                    "spec": {"key": "value", "data": ["a", "b", "c"]},
                },
            ],
            f,
        )


def write_target_file_2(target: Path, name="test.txt", change=True):
    data = ["a", "b"] + (["d"] if change else ["c"])
    with open(target / name, "w") as f:
        yaml.safe_dump_all(
            [
                {
                    "kind": "test1",
                    "metadata": {"namespace": "test"},
                    "spec": {"key": "value", "data": data},
                },
            ],
            f,
        )


@pytest.mark.parametrize(
    "migration", ["", "kapitan-0.29-to-0.30", "ignore-yaml-formatting"]
)
def test_update_catalog(
    capsys, tmp_path: Path, config: Config, fresh_cluster: Cluster, migration: str
):
    repo = catalog.fetch_catalog(config, fresh_cluster)
    upstream = git.Repo(tmp_path / "repo.git")

    config.push = True

    target = tmp_path / "compiled" / "test"
    target.mkdir(parents=True, exist_ok=True)

    _ = capsys.readouterr()

    write_target_file_1(target, name="a.yaml")
    write_target_file_1(target, name="b.yaml")
    catalog.update_catalog(config, ["test"], repo)

    captured = capsys.readouterr()
    assert upstream.active_branch.commit.message.startswith(
        "Automated catalog update from Commodore"
    )
    assert repo.repo.untracked_files == []
    assert not repo.repo.is_dirty()
    assert captured.out.startswith("Updating catalog repository...")
    assert (
        "Changes:\n     Added file manifests/a.yaml\n     Added file manifests/b.yaml\n"
        in captured.out
    )
    assert "Commiting changes..." in captured.out
    assert "Pushing catalog to remote..." in captured.out

    write_target_file_2(target, name="a.yaml")
    write_target_file_2(target, name="b.yaml", change=False)
    config.migration = migration
    catalog.update_catalog(config, ["test"], repo)

    addl_indent = ""
    # Diff with real changes is shown with correct additional
    # indent if ignore-yaml-formatting is used
    if migration != "":
        addl_indent = 2 * " "

    expected_diff = (
        "     --- manifests/a.yaml\n"
        + "     +++ manifests/a.yaml\n"
        + "     @@ -1,5 +1,3 @@\n"
        + "     -null\n"
        + "     ----\n"
        + "      kind: test1\n"
        + "      metadata:\n"
        + "        namespace: test\n"
        + "     @@ -7,6 +5,6 @@\n"
        + "        data:\n"
        + f"      {addl_indent}  - a\n"
        + f"      {addl_indent}  - b\n"
        + f"     -{addl_indent}  - c\n"
        + f"     +{addl_indent}  - d\n"
        + "        key: value\n"
    )

    if migration == "":
        # The diff of b.yaml gets suppressed by the Kapitan 0.29 to 0.30 migration
        # diffing.
        expected_diff += (
            "     --- manifests/b.yaml\n"
            + "     +++ manifests/b.yaml\n"
            + "     @@ -1,5 +1,3 @@\n"
            + "     -null\n"
            + "     ----\n"
            + "      kind: test1\n"
            + "      metadata:\n"
            + "        namespace: test\n"
        )

    captured = capsys.readouterr()
    print(captured.out)
    assert upstream.active_branch.commit.message.startswith(
        "Automated catalog update from Commodore"
    )
    assert repo.repo.untracked_files == []
    assert not repo.repo.is_dirty()
    assert captured.out.startswith("Updating catalog repository...")
    assert (" > Changes:\n" + expected_diff) in captured.out
    assert "Commiting changes..." in captured.out
    assert "Pushing catalog to remote..." in captured.out


def test_kapitan_029_030_difffunc_sorts_by_k8s_kind():
    before_text = yaml.safe_dump_all(
        [
            {"kind": "AAA", "metadata": {"namespace": "test"}},
            {"kind": "VVV"},
            {"kind": "AAA", "metadata": {"namespace": "foo"}},
            {"kind": "BBB"},
        ]
    )
    after_text = yaml.safe_dump_all(
        [
            {"kind": "AAA", "metadata": {"namespace": "test"}, "spec": {"data": ["a"]}},
            {"kind": "BBB"},
            {"kind": "AAA", "metadata": {"namespace": "foo"}},
            {"kind": "VVV"},
        ]
    )

    diffs, suppressed = catalog._kapitan_029_030_difffunc(
        before_text, after_text, fromfile="test", tofile="test"
    )

    expected_diff = (
        "--- test\n"
        + "+++ test\n"
        + "@@ -5,6 +5,9 @@\n"
        + " kind: AAA\n"
        + " metadata:\n"
        + "   namespace: test\n"
        + "+spec:\n"
        + "+  data:\n"
        + "+    - a\n"
        + " ---\n"
        + " kind: BBB\n"
        + " ---"
    )

    assert not suppressed
    assert "\n".join(diffs) == expected_diff


def test_kapitan_029_030_difffunc_suppresses_noise():
    before_text = yaml.safe_dump_all(
        [
            None,
            None,
            {
                "kind": "AAA",
                "metadata": {
                    "labels": {"app.kubernetes.io/managed-by": "Tiller"},
                },
            },
            {
                "kind": "BBB",
                "metadata": {
                    "labels": {"app.kubernetes.io/managed-by": "Tiller"},
                },
            },
            None,
            {"kind": "VVV", "metadata": {"labels": {"heritage": "Tiller"}}},
            None,
        ]
    )
    after_text = yaml.safe_dump_all(
        [
            {
                "kind": "AAA",
                "metadata": {
                    "labels": {"app.kubernetes.io/managed-by": "Helm"},
                },
            },
            {
                "kind": "BBB",
                "metadata": {
                    "labels": {"app.kubernetes.io/managed-by": "Helm"},
                },
            },
            {"kind": "VVV", "metadata": {"labels": {"heritage": "Helm"}}},
        ]
    )

    diffs, suppressed = catalog._kapitan_029_030_difffunc(
        before_text, after_text, fromfile="test", tofile="test"
    )

    print("\n".join(diffs))

    assert suppressed


def test_ignore_yaml_formatting_difffunc_keep_semantic_whitespace():
    before_text = textwrap.dedent(
        """
        a:
        b: b
        """
    )
    after_text = textwrap.dedent(
        """
        a:
          b: b
        """
    )

    diffs, suppressed = catalog._ignore_yaml_formatting_difffunc(
        before_text, after_text, fromfile="test", tofile="test"
    )

    expected_diff = (
        "--- test\n"
        + "+++ test\n"
        + "@@ -1,3 +1,3 @@\n"
        + "-a: null\n"
        + "-b: b\n"
        + "+a:\n"
        + "+  b: b\n"
        + " "
    )

    assert not suppressed
    assert "\n".join(diffs) == expected_diff


def test_ignore_yaml_formatting_difffunc_suppresses_noise():
    before_text = textwrap.dedent(
        """
        a:
        - a
        - b
        b: b
        """
    )
    after_text = textwrap.dedent(
        """
        a:
          - a
          - b
        b: b
        """
    )

    diffs, suppressed = catalog._ignore_yaml_formatting_difffunc(
        before_text, after_text, fromfile="test", tofile="test"
    )

    print("\n".join(diffs))

    assert suppressed


@responses.activate
@pytest.mark.parametrize(
    "api_resp,output,expected",
    [
        ([cluster_resp], "id", "id_single"),
        (
            [
                make_cluster_resp("c-bar"),
                make_cluster_resp("c-foo"),
                make_cluster_resp("c-test"),
            ],
            "id",
            "id_multi",
        ),
        (
            [
                make_cluster_resp("c-bar", tenant="t-foo", displayName="Bar"),
                make_cluster_resp("c-foo", tenant="t-foo", displayName="Foo"),
                make_cluster_resp("c-test"),
            ],
            "",
            "pretty_multi",
        ),
        (
            [
                make_cluster_resp("c-bar", tenant="t-foo", displayName="Bar"),
                make_cluster_resp("c-foo", tenant="t-foo", displayName="Foo"),
                make_cluster_resp("c-test"),
            ],
            "json",
            "json_multi",
        ),
        (
            [
                make_cluster_resp("c-bar", tenant="t-foo", displayName="Bar"),
                make_cluster_resp("c-foo", tenant="t-foo", displayName="Foo"),
                make_cluster_resp("c-test"),
            ],
            "yaml",
            "yaml_multi",
        ),
        (
            [
                make_cluster_resp("c-bar", tenant="t-foo", displayName="Bar"),
                make_cluster_resp("c-foo", tenant="t-foo", displayName="Foo"),
                make_cluster_resp("c-test"),
            ],
            "yml",
            "yml_multi",
        ),
    ],
)
def test_catalog_list(
    config: Config, capsys, api_resp: list, expected: str, output: str
):
    responses.add(
        responses.GET,
        "https://syn.example.com/clusters/",
        status=200,
        json=api_resp,
    )

    catalog.catalog_list(config, output)

    captured = capsys.readouterr()

    update_golden = os.getenv("COMMODORE_TESTS_GEN_GOLDEN", "False").lower() in (
        "true",
        "1",
        "t",
    )

    result = captured.out

    golden_file = (
        Path(__file__).absolute().parent / "testdata" / "catalog_list" / expected
    )
    if update_golden:
        with open(golden_file, "w") as f:
            f.write(result)
    with open(golden_file, "r") as f:
        assert result == f.read()


@responses.activate
@pytest.mark.parametrize(
    "tenant,sort_by",
    [
        ("", ""),
        ("", "id"),
        ("", "displayName"),
        ("", "tenant"),
        ("t-foo", ""),
        ("t-bar", "displayName"),
    ],
)
def test_catalog_list_parameters(config: Config, tenant: str, sort_by: str):
    params = {}

    if tenant != "":
        params["tenant"] = tenant
    if sort_by != "":
        params["sort_by"] = sort_by
    responses.add(
        responses.GET,
        "https://syn.example.com/clusters/",
        status=200,
        body="[]",
        match=[responses.matchers.query_param_matcher(params)],
    )
    catalog.catalog_list(config, "id", tenant=tenant, sort_by=sort_by)


@responses.activate
def test_catalog_list_error(config: Config):
    responses.add(
        responses.GET,
        "https://syn.example.com/clusters/",
        status=200,
        body="Not JSON",
    )

    with pytest.raises(click.ClickException) as e:
        catalog.catalog_list(config, "id")

    assert "While listing clusters on Lieutenant:" in str(e.value)
