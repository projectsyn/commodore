import json

from pathlib import Path as P

from git import Repo

from commodore.component import Component
from commodore.inventory import Inventory


def setup_directory(tmp_path: P):
    inv = Inventory(work_dir=tmp_path)
    inv.ensure_dirs()

    jsonnetfile = tmp_path / "jsonnetfile.json"
    with open(jsonnetfile, "w") as jf:
        json.dump({"version": 1, "dependencies": [], "legacyImports": True}, jf)


def test_init_existing_component(tmp_path: P):
    cn = "test-component"
    orig_url = "git@github.com:projectsyn/commodore.git"
    setup_directory(tmp_path)
    cr = Repo.init(tmp_path)
    cr.create_remote("origin", orig_url)

    c = Component(cn, directory=tmp_path)

    for url in c.repo.remote().urls:
        assert url == orig_url
