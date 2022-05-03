from pathlib import Path

import git
import yaml

from commodore import package


def test_package_init(tmp_path: Path):
    p = package.Package(
        "test",
        target_dir=tmp_path / "pkg",
        url="https://git.example.com/pkg.git",
        version="master",
    )
    assert p.url == "https://git.example.com/pkg.git"
    assert p.version == "master"
    assert p.target_dir == tmp_path / "pkg"


def _setup_package_remote(pkg_name: str, rpath: Path):
    r = git.Repo.init(rpath)
    pkg_file = f"{pkg_name}.yml"
    with open(rpath / pkg_file, "w") as f:
        yaml.safe_dump({"parameters": {pkg_name: "testing"}}, f)

    r.index.add([pkg_file])
    r.index.commit("Initial commit")


def test_package_checkout(tmp_path: Path):
    _setup_package_remote("test", tmp_path / "pkg.git")

    p = package.Package(
        "test",
        target_dir=tmp_path / "pkg",
        url=f"file://{tmp_path}/pkg.git",
        version="master",
    )
    p.checkout()

    classf = p.target_dir / "test.yml"

    assert p.target_dir.exists()
    assert p.target_dir.is_dir()
    assert classf.exists()
    assert classf.is_file()

    with open(classf, "r") as f:
        fcontents = yaml.safe_load(f)
        assert "parameters" in fcontents
        params = fcontents["parameters"]
        assert "test" in params
        assert params["test"] == "testing"
