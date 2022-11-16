from __future__ import annotations

from pathlib import Path

import click
import git

from commodore.gitrepo import diff


class MockDataStream:
    _data: str

    def __init__(self, data):
        self._data = data

    @property
    def data_stream(self):
        return self

    def read(self) -> bytes:
        return self._data.encode("utf-8")


class MockDiff:
    def __init__(self, a_path, b_path, a_blob, b_blob):
        self.a_path = a_path
        self.b_path = b_path
        self.a_blob = MockDataStream(a_blob)
        self.b_blob = MockDataStream(b_blob)


def test_compute_similarity(tmp_path: Path):
    change = MockDiff("foo.txt", "bar.txt", "foo\nbar\nbaz\n", "foo\nbar\nbar\n")

    similarity = diff._compute_similarity(change)
    expected = [
        click.style("--- bar.txt", fg="yellow"),
        click.style("+++ foo.txt", fg="yellow"),
        "Renamed file, similarity index 75.00%",
    ]
    assert similarity == expected


def test_process_diff_renamed(tmp_path: Path):
    r = git.Repo.init(tmp_path / "repo")

    with open(Path(r.working_tree_dir) / "foo.txt", "w", encoding="utf-8") as f:
        f.write("foo\nbar\nbaz\n")

    r.index.add(["foo.txt"])
    r.index.commit("Initial")

    # "Move" foo.txt to bar.txt
    (Path(r.working_tree_dir) / "foo.txt").unlink()
    with open(Path(r.working_tree_dir) / "bar.txt", "w", encoding="utf-8") as f:
        f.write("foo\nbar\nbar\n")

    r.index.remove(["foo.txt"])
    r.index.add(["bar.txt"])

    difftext: list[str] = []
    d = r.index.diff(r.head.commit)
    for ct in d.change_type:
        for c in d.iter_change_type(ct):
            print(c)
            difftext.extend(diff.process_diff(ct, c, diff.default_difffunc))

    expected = [
        click.style("Renamed file foo.txt => bar.txt", fg="yellow"),
        "\n".join(
            [
                click.style("--- foo.txt", fg="yellow"),
                click.style("+++ bar.txt", fg="yellow"),
                "Renamed file, similarity index 75.00%",
            ]
        ),
    ]
    assert difftext == expected
