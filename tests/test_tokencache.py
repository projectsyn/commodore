"""
Unit-tests for tokencache
"""
import json

from xdg.BaseDirectory import xdg_cache_home
from commodore import tokencache


def test_get_token(fs):
    fs.create_file(
        f"{xdg_cache_home}/commodore/token",
        contents='{"https://syn.example.com":{"id_token": "thetoken"},'
        + '"https://syn2.example.com":{"id_token": "token2"}}',
    )
    assert tokencache.get("https://syn.example.com") == {"id_token": "thetoken"}
    assert tokencache.get("https://syn2.example.com") == {"id_token": "token2"}


def test_get_nonexistent_token(fs):
    fs.create_file(
        f"{xdg_cache_home}/commodore/token",
        contents='{"https://syn.example.com":{"id_token":"token"},'
        + '"https://syn2.example.com":{"id_token":"token2"}}',
    )
    assert tokencache.get("https://syn3.example.com") == {}


def test_ignore_broken_json_cache(fs):
    fs.create_file(
        f"{xdg_cache_home}/commodore/token",
        contents='{"https://syn.example.com":{"id_token":"token"}',
    )
    assert tokencache.get("https://syn.example.com") == {}


def test_save_token(fs):
    tokencache.save("https://syn.example.com", {"id_token": "save"})
    tokencache.save("https://syn2.example.com", {"id_token": "save2"})

    with open(f"{xdg_cache_home}/commodore/token") as f:
        cache = json.load(f)
        assert cache == {
            "https://syn.example.com": {"id_token": "save"},
            "https://syn2.example.com": {"id_token": "save2"},
        }


def test_save_and_get_token(fs):
    tokencache.save("https://syn.example.com", {"id_token": "token"})
    tokencache.save("https://syn2.example.com", {"id_token": "token2"})
    tokencache.save("https://syn3.example.com", {"id_token": "token3"})
    tokencache.save("https://syn2.example.com", {"id_token": "Foo"})

    assert tokencache.get("https://syn.example.com") == {"id_token": "token"}
    assert tokencache.get("https://syn2.example.com") == {"id_token": "Foo"}
    assert tokencache.get("https://syn3.example.com") == {"id_token": "token3"}


def test_drop_old_cache_entry(fs):
    fs.create_file(
        f"{xdg_cache_home}/commodore/token",
        contents='{"https://syn.example.com":"thetoken",'
        + '"https://syn2.example.com":{"id_token": "token2"}}',
    )
    assert tokencache.get("https://syn.example.com") == {}
    assert tokencache.get("https://syn2.example.com") == {"id_token": "token2"}


def test_update_broken_json_cache(fs):
    cachef = fs.create_file(
        f"{xdg_cache_home}/commodore/token",
        contents='{"https://syn.example.com":{"id_token":"token"}',
    )
    tokencache.save("https://syn2.example.com", {"id_token": "token2"})
    assert tokencache.get("https://syn2.example.com") == {"id_token": "token2"}
    assert (
        cachef.contents
        == '{\n "https://syn2.example.com": {\n  "id_token": "token2"\n }\n}'
    )

    tokencache.save("https://syn.example.com", {"id_token": "token"})

    assert tokencache.get("https://syn2.example.com") == {"id_token": "token2"}
    assert tokencache.get("https://syn.example.com") == {"id_token": "token"}
