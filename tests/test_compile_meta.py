import os

from pathlib import Path

from commodore.config import Config
from commodore.gitrepo import GitRepo

from commodore.catalog import CompileMeta


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
        "ssh://git@git.example.com/global-defaults",
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


def test_compile_meta_render_catalog_commit_message_no_leading_newline(
    config: Config, tmp_path: Path
):
    _setup_config_repos(config)

    compile_meta = CompileMeta(config)

    commit_message = compile_meta.render_catalog_commit_message()

    assert not commit_message.startswith("\n")
    assert commit_message.startswith("Automated catalog update from Commodore\n\n")
