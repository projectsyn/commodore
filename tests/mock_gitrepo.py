from pathlib import Path
from typing import Optional


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
    def __init__(self):
        self.head = Head()


class GitRepo:
    def __init__(
        self,
        remote: str,
        targetdir: Path,
        force_init=False,
        author_name: Optional[str] = None,
        author_email: Optional[str] = None,
        config=None,
    ):
        self.remote = remote
        self.targetdir = targetdir
        self.config = config
        self.repo = Repo()
        self.version = None

        self.call_counts = {
            "commit": 0,
            "checkout": 0,
        }

    def checkout(self, rev):
        self.call_counts["checkout"] += 1
        self.version = rev

    def commit(self, rev):
        self.call_counts["commit"] += 1
        return rev
