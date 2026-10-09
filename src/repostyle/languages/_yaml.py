"""YAML comment extraction and folded block scalar scanning."""

from __future__ import annotations

import re
from collections.abc import Iterator

from repostyle.languages._model import CommentToken, comment_at

# A YAML block scalar introducer: a value that, after a `:` or `-` lead or
# standing at the line start, is a `|` or `>` carrying only chomping and indent
# indicators, so the indented lines that follow are literal.
_BLOCK_SCALAR_PATTERN = re.compile(r"(?:[:-]\s+|^\s*)[|>][0-9+-]*\s*$")

# The folded subset of that introducer: a `>` carrying at most a chomping
# indicator. A folded scalar's single line breaks fold to spaces, so rewrapping
# its lines leaves the value unchanged, which a literal `|` scalar -- whose
# breaks are content -- would not survive. An explicit indentation indicator
# (`>2`) is excluded rather than honoured, since it puts the content indent
# somewhere other than where this scan infers it.
_FOLDED_SCALAR_PATTERN = re.compile(r"(?:[:-]\s+|^\s*)>[+-]?\s*$")


def folded_runs(source: str) -> Iterator[tuple[int, ...]]:
    """Yields the fillable runs inside each folded block scalar in `source`."""
    lines = source.splitlines()
    for introducer, stop in folded_scalars(source):
        yield from _body_runs(lines, introducer + 1, stop)


def _body_runs(lines: list[str], start: int, stop: int) -> Iterator[tuple[int, ...]]:
    """Yields the runs of foldable lines in one scalar body.

    The body's indent is the first non-blank line's, as YAML reads it. A line
    at that indent and free of trailing whitespace folds to a space and joins
    the open run; any other line closes it.
    """
    body = [index for index in range(start, stop) if lines[index].strip()]
    if not body:
        return
    indent = _indent_of(lines[body[0]])
    run: list[int] = []
    for index in range(start, stop):
        line = lines[index]
        if line.strip() and _indent_of(line) == indent and line == line.rstrip():
            run.append(index + 1)
            continue
        if run:
            yield tuple(run)
        run = []
    if run:
        yield tuple(run)


def folded_scalars(source: str) -> Iterator[tuple[int, int]]:
    """Yields each folded block scalar as `(introducer index, stop index)`.

    Both are 0-based indexes into the lines of `source`, and `stop` is
    exclusive, so the scalar's content is the lines between them. Every block
    scalar is stepped over as a unit, so a `#` or a nested-looking introducer
    among the literal lines of a `|` scalar opens nothing.
    """
    lines = source.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        column = _yaml_comment_column(line)
        content = line if column is None else line[:column]
        if not _opens_block_scalar(content):
            index += 1
            continue
        stop = index + 1
        introducer_indent = _indent_of(line)
        while stop < len(lines) and _inside_block(lines[stop], introducer_indent):
            stop += 1
        if _FOLDED_SCALAR_PATTERN.search(content):
            yield index, stop
        index = stop


def yaml_comments(source: str) -> Iterator[CommentToken]:
    """Yields each `#` comment in YAML `source`, line by line.

    A `|` or `>` block scalar records its introducer indent in `block_indent`;
    the deeper-indented lines that follow are literal, so a `#` among them is
    never read as a comment.
    """
    block_indent: int | None = None
    for lineno, line in enumerate(source.splitlines(), start=1):
        if block_indent is not None and _inside_block(line, block_indent):
            continue
        block_indent = None
        column = _yaml_comment_column(line)
        content = line if column is None else line[:column]
        if _opens_block_scalar(content):
            block_indent = _indent_of(line)
        if column is not None:
            yield comment_at(lineno, line, column)


def _inside_block(line: str, block_indent: int) -> bool:
    """Reports whether `line` sits in a block scalar at `block_indent`."""
    return not line.strip() or _indent_of(line) > block_indent


def _indent_of(line: str) -> int:
    """Returns the count of leading spaces on `line`."""
    return len(line) - len(line.lstrip(" "))


def _opens_block_scalar(content: str) -> bool:
    """Reports whether `content` is a YAML line opening a block scalar."""
    return _BLOCK_SCALAR_PATTERN.search(content) is not None


def _yaml_comment_column(line: str) -> int | None:
    """Returns the column of a `#` comment in one YAML line, or `None`.

    A `#` opens a comment only at the line start or after whitespace, and never
    inside a quoted scalar. A double-quoted scalar honours backslash escapes; a
    single-quoted one escapes a quote by doubling it.
    """
    index = 0
    while index < len(line):
        char = line[index]
        if char == "#" and (index == 0 or line[index - 1] in " \t"):
            return index
        if char == '"':
            index = _skip_yaml_double(line, index)
            continue
        if char == "'":
            index = _skip_yaml_single(line, index)
            continue
        index += 1
    return None


def _skip_yaml_double(line: str, index: int) -> int:
    """Returns the index past the double-quoted scalar opening at `index`."""
    index += 1
    while index < len(line):
        if line[index] == "\\":
            index += 2
            continue
        if line[index] == '"':
            return index + 1
        index += 1
    return len(line)


def _skip_yaml_single(line: str, index: int) -> int:
    """Returns the index past the single-quoted scalar opening at `index`."""
    index += 1
    while index < len(line):
        if line[index] == "'":
            if line[index + 1 : index + 2] == "'":
                index += 2
                continue
            return index + 1
        index += 1
    return len(line)
