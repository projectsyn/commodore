from url_normalize import url_normalize
from url_normalize.tools import deconstruct_url, reconstruct_url


def normalize_url(url: str) -> str:
    nurl = url_normalize(url)
    if not nurl:
        raise ValueError(f"url_normalize returned None for {url}")
    return nurl


def _normalize_git_ssh(url: str) -> str:
    # Import url_normalize internal methods here, so they're not visible in the file
    # scope of gitrepo.py
    # pylint: disable=import-outside-toplevel
    from url_normalize.url_normalize import (
        normalize_userinfo,
        normalize_host,
        normalize_path,
        provide_url_scheme,
    )

    if "@" in url and not url.startswith("ssh://"):
        # Assume git@host:repo format, reformat so url_normalize understands
        # the URL
        host, repo = url.split(":")
        url = f"{host}/{repo}"
    # Reuse normalization logic from url_normalize, simplify for Git-SSH use case.
    # We can't do `url_normalize(url, "ssh"), because the library doesn't know "ssh" as
    # a scheme, and fails to look up the default port for "ssh".
    url = provide_url_scheme(url, "ssh")
    urlparts = deconstruct_url(url)
    urlparts = urlparts._replace(
        userinfo=normalize_userinfo(urlparts.userinfo),
        host=normalize_host(urlparts.host),
        path=normalize_path(urlparts.path, scheme="https"),
    )
    return reconstruct_url(urlparts)


def normalize_git_url(url: str) -> str:
    """Normalize HTTP(s) and SSH Git URLs"""
    if "@" in url and ("://" not in url or url.startswith("ssh://")):
        url = _normalize_git_ssh(url)
    elif url.startswith("http://") or url.startswith("https://"):
        nurl = url_normalize(url)
        if not nurl:
            # NOTE(sg): This should be unreachable, since url_normalize() only
            # returns None when passed None as the url to normalize. However, we
            # need the check to make mypy happy.
            raise ValueError(f"failed to normalize {url}")
        url = nurl
    return url
