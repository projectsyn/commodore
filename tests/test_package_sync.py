from __future__ import annotations

from pathlib import Path

import git
import pytest

from test_package import _setup_package_remote

from commodore.config import Config
from commodore.package import Package
from commodore.package import sync


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
