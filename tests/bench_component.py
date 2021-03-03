from pathlib import Path
from typing import Iterable

import git
import pytest

from commodore.component import Component


def setup_components_upstream(tmp_path: Path, components: Iterable[str]):
    # Prepare minimum component directories
    upstream = tmp_path / "upstream"
    component_urls = {}
    component_versions = {}
    for component in components:
        repo_path = upstream / component
        component_urls[component] = f"file://#{repo_path.resolve()}"
        component_versions[component] = None
        repo = git.Repo.init(repo_path)

        class_dir = repo_path / "class"
        class_dir.mkdir(parents=True, exist_ok=True)
        (class_dir / "defaults.yml").touch(exist_ok=True)

        repo.index.add(["class/defaults.yml"])
        repo.index.commit("component defaults")

    return component_urls, component_versions


def _setup_component(tmp_path: Path, cn: str):
    urls, _ = setup_components_upstream(tmp_path, [cn])
    return Component(cn, repo_url=urls[cn], directory=tmp_path / "test-component")


@pytest.mark.bench
def bench_component_checkout(benchmark, tmp_path: Path):
    c = _setup_component(tmp_path, "test-component")
    benchmark(c.checkout)
