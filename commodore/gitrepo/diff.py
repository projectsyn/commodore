from __future__ import annotations

import difflib

from collections.abc import Iterable
from typing import Protocol

import click


class DiffFunc(Protocol):
    def __call__(
        self, before_text: str, after_text: str, fromfile: str = "", tofile: str = ""
    ) -> tuple[Iterable[str], bool]:
        ...


def _colorize_diff(line: str) -> str:
    if line.startswith("--- ") or line.startswith("+++ ") or line.startswith("@@ "):
        return click.style(line, fg="yellow")
    if line.startswith("+"):
        return click.style(line, fg="green")
    if line.startswith("-"):
        return click.style(line, fg="red")
    return line


def _compute_similarity(change):
    before = change.b_blob.data_stream.read().decode("utf-8").split("\n")
    after = change.a_blob.data_stream.read().decode("utf-8").split("\n")
    r = difflib.SequenceMatcher(a=before, b=after).ratio()
    similarity_diff = []
    similarity_diff.append(click.style(f"--- {change.b_path}", fg="yellow"))
    similarity_diff.append(click.style(f"+++ {change.a_path}", fg="yellow"))
    similarity_diff.append(f"Renamed file, similarity index {r * 100:.2f}%")
    return similarity_diff


def default_difffunc(
    before_text: str, after_text: str, fromfile: str = "", tofile: str = ""
) -> tuple[Iterable[str], bool]:
    before_lines = before_text.split("\n")
    after_lines = after_text.split("\n")
    diff_lines = difflib.unified_diff(
        before_lines, after_lines, lineterm="", fromfile=fromfile, tofile=tofile
    )
    # never suppress diffs in default difffunc
    return diff_lines, False


def process_diff(change_type: str, change, diff_func: DiffFunc) -> Iterable[str]:
    difftext = []
    # Because we're diffing the staged changes, the diff objects
    # are backwards, and "added" files are actually being deleted
    # and vice versa for "deleted" files.
    if change_type == "A":
        difftext.append(click.style(f"Deleted file {change.b_path}", fg="red"))
    elif change_type == "D":
        difftext.append(click.style(f"Added file {change.b_path}", fg="green"))
    elif change_type == "R":
        difftext.append(
            click.style(f"Renamed file {change.b_path} => {change.a_path}", fg="yellow")
        )
    else:
        # Other changes should produce a usable diff
        # The diff objects are backwards, so use b_blob as before
        # and a_blob as after.
        before = change.b_blob.data_stream.read().decode("utf-8")
        after = change.a_blob.data_stream.read().decode("utf-8")
        diff_lines, suppress_diff = diff_func(
            before, after, fromfile=change.b_path, tofile=change.a_path
        )
        if not suppress_diff:
            if change.renamed_file:
                # Just compute similarity ratio for renamed files
                # similar to git's diffing
                difftext.append("\n".join(_compute_similarity(change)).strip())
            else:
                diff_lines = [_colorize_diff(line) for line in diff_lines]
                difftext.append("\n".join(diff_lines).strip())

    return difftext
