"""
Unit-tests for helpers
"""
from pathlib import Path

import commodore.helpers as helpers
from commodore.config import Config
from commodore.component import Component, component_dir


def test_apierror():
    e = helpers.ApiError("test")
    assert f"{e}" == "test"

    try:
        raise helpers.ApiError("test2")
    except helpers.ApiError as e2:
        assert f"{e2}" == "test2"


def test_clean_working_tree(tmp_path: Path):
    cfg = Config(work_dir=tmp_path)
    cfg.inventory.ensure_dirs()
    d = component_dir(tmp_path, "test")
    assert not d.is_dir()
    Component("test", work_dir=tmp_path)
    assert d.is_dir()
    helpers.clean_working_tree(cfg)
    assert d.is_dir()
