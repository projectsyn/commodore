from commodore import git


class Head:
    def __init__(self):
        self._reference = None
        self.call_counts = {
            "reference": 0,
            "reference.setter": 0,
            "reset": 0,
        }

    @property
    def reference(self):
        self.call_counts["reference"] += 1
        return self._reference

    @reference.setter
    def reference(self, ref):
        self.call_counts["reference.setter"] += 1
        self._reference = ref

    def reset(self, **kwargs):
        self.call_counts["reset"] += 1
        pass


class Repo:
    def __init__(self, url, directory, cfg):
        self.url = url
        self.directory = directory
        self.config = cfg
        self.head = Head()

        self.call_counts = {
            "commit": 0,
            "checkout_version": 0,
        }

    def commit(self, rev):
        self.call_counts["commit"] += 1
        return rev


def clone_repository(url, directory, cfg):
    return Repo(url, directory, cfg)


def checkout_version(repo, rev):
    repo.call_counts["checkout_version"] += 1
    git.checkout_version(repo, rev)
