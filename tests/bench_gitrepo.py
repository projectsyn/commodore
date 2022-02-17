from pathlib import Path

import git
import pytest

from commodore import gitrepo


def setup_remote(tmp_path: Path):
    # Prepare minimum component directories
    remote = tmp_path / "remote.git"
    repo = git.Repo.init(remote)

    (remote / "test.txt").touch(exist_ok=True)

    repo.index.add(["test.txt"])
    repo.index.commit("initial commit")

    return f"file://{remote.absolute()}"


@pytest.mark.bench
def bench_component_checkout(benchmark, tmp_path: Path):
    repo_url = setup_remote(tmp_path)
    r = gitrepo.GitRepo(repo_url, tmp_path / "local", force_init=True)
    benchmark(r.checkout)
