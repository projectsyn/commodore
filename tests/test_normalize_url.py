import pytest
from commodore import normalize_url


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://example.com", "https://example.com/"),
        ("https://example.com//foo", "https://example.com/foo"),
    ],
)
def test_normalize_url(url: str, expected: str):
    nurl = normalize_url.normalize_url(url)
    assert nurl == expected


def test_normalize_url_raises_on_none():
    with pytest.raises(ValueError, match="url_normalize returned None for None"):
        _ = normalize_url.normalize_url(None)


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://git.example.com//foo/bar.git", "https://git.example.com/foo/bar.git"),
        (
            "https://user@git.example.com/path/to////repo.git",
            "https://user@git.example.com/path/to/repo.git",
        ),
        ("user@host:path/to/repo.git", "ssh://user@host/path/to/repo.git"),
        ("ssh://user@host///path/to/repo.git", "ssh://user@host/path/to/repo.git"),
        (
            "ssh://user@host:2222/path////to/repo.git",
            "ssh://user@host:2222/path/to/repo.git",
        ),
    ],
)
def test_normalize_git_url(url: str, expected: str):
    nurl = normalize_url.normalize_git_url(url)
    assert nurl == expected
