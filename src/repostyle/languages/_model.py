"""The records a language contributes: its comments, block spans, and hooks."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import NamedTuple


class CommentToken(NamedTuple):
    lineno: int
    """1-based line the comment starts on."""
    column: int
    """0-based column of the comment marker."""
    string: str
    """The comment from its marker to the end of the line."""
    is_trailing: bool
    """Whether code or data precedes the comment on its line."""


def comment_at(lineno: int, line: str, column: int) -> CommentToken:
    """Builds a comment token for the marker at `column` on `line`."""
    return CommentToken(lineno, column, line[column:], bool(line[:column].strip()))


def comment_text(comment: str) -> str:
    """Returns a comment's prose, stripped of its leading marker and space.

    The marker is every leading `#` of a hash comment or every leading `/` of a
    `//` comment, so the result reads the same whichever language wrote it.
    """
    return _MARKER_PATTERN.sub("", comment, count=1).strip()


_MARKER_PATTERN = re.compile(r"^(?:#+|//+)")

CommentScanner = Callable[[str], Iterator[CommentToken]]

SpanScanner = Callable[[str], Iterator[tuple[int, int]]]

PathPredicate = Callable[[Path], bool]


def _is_unclaimed(path: Path) -> bool:
    """Reports no path as a test, for a language without test files."""
    del path
    return False


def _no_spans(source: str) -> Iterator[tuple[int, int]]:
    """Yields no block spans, for a language without nested blocks."""
    del source
    yield from ()


class Language(NamedTuple):
    """One source language repostyle reads, and the hooks that read it.

    A rule that reads comments, block spans, or test layout goes through these
    hooks, so it reaches every language that supplies them without naming any.
    """

    name: str
    """The lowercase id configuration and rule bindings name it by."""
    suffixes: frozenset[str]
    """The file suffixes, dot included, that hold this language."""
    is_default: bool
    """Whether a repo lints it without listing it under `languages`."""
    comments: CommentScanner | None = None
    """Yields the line comments of a source, or `None` for no comments."""
    block_spans: SpanScanner = _no_spans
    """Yields the inclusive line span of each block a directive can cover."""
    is_test_file: PathPredicate = _is_unclaimed
    """Reports whether a path holds tests in this language's layout."""
