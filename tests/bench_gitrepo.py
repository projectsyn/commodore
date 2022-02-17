from pathlib import Path

import pytest

from commodore import gitrepo

from test_gitrepo import setup_remote


@pytest.mark.bench
def bench_component_checkout(benchmark, tmp_path: Path):
    repo_url, _ = setup_remote(tmp_path)
    r = gitrepo.GitRepo(repo_url, tmp_path / "local", force_init=True)
    benchmark(r.checkout)
