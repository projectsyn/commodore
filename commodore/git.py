import difflib, click

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

def _colorize_diff(line):
    if line.startswith('---') or line.startswith('+++'):
        return click.style(line, fg='yellow')
    if line.startswith('+'):
        return click.style(line, fg='green')
    if line.startswith('-'):
        return click.style(line, fg='red')
    return line

def stage_all(repo):
    index = repo.index
    dels = index.diff(None)
    index.add('*')
    diff = index.diff(repo.head.commit)
    changed = False
    difftext = []
    if diff:
        changed = True
        for ct in diff.change_type:
            for c in diff.iter_change_type(ct):
                # Because we're diffing the staged changes, the diff objects
                # are backwards, and "added" files are actually being deleted
                # and vice versa for "deleted" files.
                if ct == 'A':
                    difftext.append(click.style(f"Deleted file {c.b_path}", fg='red'))
                elif ct == 'D':
                    difftext.append(click.style(f"Added file {c.b_path}", fg='green'))
                else:
                    # Other change types should produce a usable diff
                    # The diff objects are backwards, so use b_blob as before
                    # and a_blob as after.
                    before = c.b_blob.data_stream.read().decode('utf-8').split('\n')
                    after = c.a_blob.data_stream.read().decode('utf-8').split('\n')
                    u = difflib.unified_diff(before, after, lineterm='',
                            fromfile=c.b_path, tofile=c.a_path)
                    u = [ _colorize_diff(l) for l in u ]
                    difftext.append('\n'.join(u).strip())
    if dels:
        changed = True
        to_remove = []
        for c in dels.iter_change_type('D'):
            difftext.append(click.style(f"Deleted file {c.b_path}", fg='red'))
            to_remove.append(c.b_path)
        index.remove(items=to_remove)
    return '\n'.join(difftext), changed
