"""
Tests for catalog internals
"""

from commodore.catalog import _render_catalog_commit_msg
from commodore.config import Config


def test_catalog_commit_message():
    config = Config(
        "https://syn.example.com", "token", "ssh://git@git.example.com", False
    )

    commit_message = _render_catalog_commit_msg(config)
    assert not commit_message.startswith("\n")
    assert commit_message.startswith("Automated catalog update from Commodore\n\n")
