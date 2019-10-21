from git import Repo

from .config import VersionType

def _normalize_git_ssh(url):
    from url_normalize.url_normalize import normalize_userinfo, normalize_host, \
                                            normalize_path, provide_url_scheme
    from url_normalize.tools import deconstruct_url, reconstruct_url

    origurl = url
    if '@' in url and not url.startswith('ssh://'):
        # Assume git@host:repo format, reformat so url_normalize understands
        # the URL
        host, repo = url.split(':')
        url = f"{host}/{repo}"
    # Import heavy lifting from url_normalize, simplify for Git-SSH usecase
    url = provide_url_scheme(url, "ssh")
    urlparts = deconstruct_url(url)
    urlparts = urlparts._replace(
            userinfo=normalize_userinfo(urlparts.userinfo),
            host=normalize_host(urlparts.host),
            path=normalize_path(urlparts.path, scheme='https'),
    )
    return reconstruct_url(urlparts)


class RefError(ValueError):
    def __init__(self, message):
        self.message = message

def _tag_name(tagref):
    """
    Remove `refs/tags` from tag path
    """
    _refs, _tags, tag = tagref.path.split('/', 2)
    assert(_refs == "refs")
    assert(_tags == "tags")
    return tag

def checkout_version(repo, version):
    """
    Checkout `ref` in `repo`.
    First check if `ref` is a tag on the repository, if so, check out that
    tag. Otherwise, check if `ref` is a branch, if so, checkout that branch.
    Otherwise, if `ref` is a commit id, checkout that commit.

    If `ref` is not pointing to a known commit in the repo, raise an
    Exception.
    """
    if version.type == VersionType.tag:
        tags = list(map(_tag_name, repo.tags))
        try:
            tidx = tags.index(version.ref)
        except ValueError as e:
            raise RefError(f"Unknown tag {version.ref}") from e
        repo.head.reference = tags[tidx]
    elif version.type == VersionType.branch:
        branches = list(map(lambda h: h.name, repo.heads))
        try:
            bidx = branches.index(version.ref)
        except ValueError as e:
            raise RefError(f"Unknown branch {version.ref}") from e
        repo.head.reference = repo.heads[bidx]
    elif version.type == VersionType.ref:
        repo.head.reference = repo.commit(version.ref)
    else:
        raise RefError(f"Unknown version type {version.type.name}")

    repo.head.reset(index=True, working_tree=True)

def clone_repository(repository_url, directory):
    return Repo.clone_from(_normalize_git_ssh(repository_url), directory)
