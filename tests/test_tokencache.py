"""
Unit-tests for tokencache
"""
import json

from xdg.BaseDirectory import xdg_cache_home
from commodore import tokencache


def test_get_token(fs):
    fs.create_file(
        f"{xdg_cache_home}/commodore/token",
        contents='{"https://syn.example.com":"token","https://syn2.example.com":"token2"}',
    )
    assert tokencache.get("https://syn.example.com") == "token"
    assert tokencache.get("https://syn2.example.com") == "token2"


def test_get_nonexistent_token(fs):
    fs.create_file(
        f"{xdg_cache_home}/commodore/token",
        contents='{"https://syn.example.com":"token","https://syn2.example.com":"token2"}',
    )
    assert tokencache.get("https://syn3.example.com") is None


def test_save_token(fs):
    tokencache.save("https://syn.example.com", "save")
    tokencache.save("https://syn2.example.com", "save2")

    with open(f"{xdg_cache_home}/commodore/token") as f:
        cache = json.load(f)
        assert cache == {
            "https://syn.example.com": "save",
            "https://syn2.example.com": "save2",
        }


def test_save_and_get_token(fs):
    tokencache.save("https://syn.example.com", "token")
    tokencache.save("https://syn2.example.com", "token2")
    tokencache.save("https://syn3.example.com", "token3")
    tokencache.save("https://syn2.example.com", "Foo")

    assert tokencache.get("https://syn.example.com") == "token"
    assert tokencache.get("https://syn2.example.com") == "Foo"
    assert tokencache.get("https://syn3.example.com") == "token3"
