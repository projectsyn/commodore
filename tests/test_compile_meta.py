import os

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import git
import pytest
import responses

from responses import matchers

from commodore.config import Config
from commodore.dependency_mgmt import fetch_components, fetch_packages
from commodore.gitrepo import GitRepo

from test_dependency_mgmt import setup_components_upstream, _setup_packages

from commodore.catalog import CompileMeta
from commodore.cluster import report_compile_metadata


def _setup_config_repos(cfg: Config, tenant="t-test-tenant"):
    os.makedirs(cfg.inventory.inventory_dir)
    global_repo = GitRepo(
        "ssh://git@git.example.com/global-defaults",
        cfg.inventory.global_config_dir,
        force_init=True,
    )
    with open(
        cfg.inventory.global_config_dir / "commodore.yml", "w", encoding="utf-8"
    ) as f:
        f.write("---\n")
    global_repo.stage_all()
    global_repo.commit("Initial commit")
    cfg.register_config("global", global_repo)

    tenant_repo = GitRepo(
        "ssh://git@git.example.com/test-tenant",
        cfg.inventory.tenant_config_dir(tenant),
        force_init=True,
    )
    with open(
        cfg.inventory.tenant_config_dir(tenant) / "common.yml",
        "w",
        encoding="utf-8",
    ) as f:
        f.write("---\n")
    tenant_repo.stage_all()
    tenant_repo.commit("Initial commit")
    cfg.register_config("customer", tenant_repo)

    return (global_repo.repo.head.commit.hexsha, tenant_repo.repo.head.commit.hexsha)


def test_compile_meta_render_catalog_commit_message_no_leading_newline(
    config: Config, tmp_path: Path
):
    _setup_config_repos(config)

    compile_meta = CompileMeta(config)

    commit_message = compile_meta.render_catalog_commit_message()

    assert not commit_message.startswith("\n")
    assert commit_message.startswith("Automated catalog update from Commodore\n\n")


@patch("commodore.dependency_mgmt._read_components")
@patch("commodore.dependency_mgmt._discover_components")
@patch("commodore.dependency_mgmt._read_packages")
@patch("commodore.dependency_mgmt._discover_packages")
def test_compile_meta_creation(
    patch_discover_packages,
    patch_read_packages,
    patch_discover_components,
    patch_read_components,
    config: Config,
    tmp_path: Path,
):
    components = ["foo", "bar", "baz", "qux"]
    packages = ["foo", "bar"]

    # setup mock components
    patch_discover_components.return_value = (components, {})
    # setup_components_upstream sets version=None for all components
    cdeps = setup_components_upstream(tmp_path, components)

    # NOTE: We assume that setup_components_upstream creates upstream repos in
    # `tmp_path/upstream/<component-name>`
    crepos = {cn: git.Repo(tmp_path / "upstream" / cn) for cn in components}

    crepos["foo"].version = "master"
    crepos["bar"].create_tag("v1.2.3")
    cdeps["bar"].version = "v1.2.3"
    cdeps["baz"].version = crepos["baz"].head.commit.hexsha

    patch_read_components.return_value = cdeps

    # setup mock packages
    patch_discover_packages.return_value = packages
    pdeps = _setup_packages(tmp_path / "packages_upstream", packages)
    prepos = {
        pkg: git.Repo(tmp_path / "packages_upstream" / f"{pkg}.git") for pkg in packages
    }

    patch_read_packages.return_value = pdeps

    # setup mock tenant&global repo
    global_sha, tenant_sha = _setup_config_repos(config)

    # use regular logic to fetch mocked packages & components
    fetch_packages(config)
    fetch_components(config)

    config.get_components()["qux"]._sub_path = "component"

    aliases = {cn: cn for cn in components}
    # create alias to verify instance reporting
    aliases["quxxer"] = "qux"
    config.register_component_aliases(aliases)

    meta = CompileMeta(config)
    meta_dict = meta.as_dict()
    assert set(meta_dict.keys()) == {
        "commodoreBuildInfo",
        "global",
        "instances",
        "lastCompile",
        "packages",
        "tenant",
    }

    assert set(meta_dict["commodoreBuildInfo"].keys()) == {"gitVersion", "version"}
    # dummy value that's overwritten by the release CI
    assert meta_dict["commodoreBuildInfo"]["gitVersion"] == "0"
    # dummy value that's overwritten by the release CI
    assert meta_dict["commodoreBuildInfo"]["version"] == "0.0.0"

    # sanity check last compile timestamp. We can't check an exact value but it should
    # be <1s in the past regardless of how slow the test is. We expect the last compile
    # timestamp to be in ISO format with a timezone. If that isn't the case the
    # conversion or comparison should raise an exception.
    assert datetime.now().astimezone() - datetime.fromisoformat(
        meta_dict["lastCompile"]
    ) < timedelta(seconds=1)

    # check instances
    assert set(meta_dict["instances"].keys()) == {"foo", "bar", "baz", "qux", "quxxer"}
    for alias, info in meta_dict["instances"].items():
        cn = alias[0:3]
        assert len({"url", "version", "gitSha", "component"} - set(info.keys())) == 0
        assert info["component"] == cn
        assert info["url"] == cdeps[cn].url
        # NOTE(sg): We currently make sure that the tests use an empty gitconfig which
        # means that we should always get "master" as the default branch.
        assert info["version"] == cdeps[cn].version or "master"
        assert info["gitSha"] == crepos[cn].head.commit.hexsha
    assert "path" in meta_dict["instances"]["qux"]
    assert "path" in meta_dict["instances"]["quxxer"]
    assert meta_dict["instances"]["qux"]["path"] == "component"
    assert meta_dict["instances"]["quxxer"]["path"] == "component"

    # check packages
    assert set(meta_dict["packages"].keys()) == {"foo", "bar"}
    for pkg, info in meta_dict["packages"].items():
        assert set(info.keys()) == {"url", "version", "gitSha"}
        assert info["url"] == pdeps[pkg].url
        assert info["version"] == pdeps[pkg].version or "master"
        assert info["gitSha"] == prepos[pkg].head.commit.hexsha

    # check global & tenant version info
    assert set(meta_dict["global"].keys()) == {"url", "version", "gitSha"}
    assert meta_dict["global"]["url"] == "ssh://git@git.example.com/global-defaults"
    assert meta_dict["global"]["version"] == "master"
    assert meta_dict["global"]["gitSha"] == global_sha
    assert set(meta_dict["tenant"].keys()) == {"url", "version", "gitSha"}
    assert meta_dict["tenant"]["url"] == "ssh://git@git.example.com/test-tenant"
    assert meta_dict["tenant"]["version"] == "master"
    assert meta_dict["tenant"]["gitSha"] == tenant_sha


def test_compile_meta_config_overrides(tmp_path: Path, config: Config):
    # NOTE: The CompileMeta initialization doesn't validate that the checked out
    # revision of the repo matches the version override.
    global_sha, tenant_sha = _setup_config_repos(config)
    config.tenant_repo_revision_override = "feat/test"
    config.global_repo_revision_override = global_sha[0:10]

    compile_meta = CompileMeta(config)

    assert compile_meta.global_repo.version == global_sha[0:10]
    assert compile_meta.global_repo.git_sha == global_sha
    assert compile_meta.tenant_repo.version == "feat/test"
    assert compile_meta.tenant_repo.git_sha == tenant_sha


@pytest.mark.parametrize("report", [False, True])
@responses.activate
def test_report_compile_meta(tmp_path: Path, config: Config, capsys, report):
    _setup_config_repos(config, "t-tenant-1234")
    config.update_verbosity(1)

    compile_meta = CompileMeta(config)
    responses.add(
        responses.POST,
        f"{config.api_url}/clusters/c-cluster-1234/compileMeta",
        content_type="application/json",
        status=204,
        body=None,
        match=[matchers.json_params_matcher(compile_meta.as_dict())],
    )
    report_compile_metadata(config, compile_meta, "c-cluster-1234", report)

    captured = capsys.readouterr()
    if report:
        assert captured.out.startswith(
            " > The following compile metadata will be reported to Lieutenant:\n"
        )
    else:
        assert captured.out.startswith(
            " > The following compile metadata would be reported to Lieutenant on a successful catalog push:\n"
        )
