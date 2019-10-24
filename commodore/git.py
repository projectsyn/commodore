import difflib

from git import Repo
from git.exc import GitCommandError, BadName

class RefError(ValueError):
    def __init__(self, message):
        self.message = message

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


def checkout_version(repo, ref):
    """
    Checkout `ref` in `repo`. Always checkout as detached HEAD as that
    massively simplifies the implementation.
    """
    try:
        repo.head.reference = repo.commit(f"remotes/origin/{ref}")
        repo.head.reset(index=True, working_tree=True)
    except GitCommandError as e:
        raise RefError(f"Failed to checkout revision '{ref}'") from e
    except BadName as e:
        raise RefError(f"Revision '{ref}' not found in repository") from e

def clone_repository(repository_url, directory):
    return Repo.clone_from(_normalize_git_ssh(repository_url), directory)

def init_repository(path):
    return Repo(path)
