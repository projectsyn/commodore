"""
Tests for catalog internals
"""

from commodore.catalog import _render_catalog_commit_msg
from commodore.config import Config


def test_catalog_commit_message(tmp_path):
    config = Config(
        tmp_path,
        api_url="https://syn.example.com",
        api_token="token",
    )

    commit_message = _render_catalog_commit_msg(config)
    assert not commit_message.startswith("\n")
    assert commit_message.startswith("Automated catalog update from Commodore\n\n")
