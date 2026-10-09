"""TOML comment extraction."""

from __future__ import annotations

from collections.abc import Iterator

from repostyle.languages._model import CommentToken, comment_at


def toml_comments(source: str) -> Iterator[CommentToken]:
    """Yields each `#` comment in TOML `source`, line by line.

    A multi-line string spanning lines carries its closing delimiter forward in
    `open_delimiter`, so a `#` inside it is never a comment.
    """
    open_delimiter: str | None = None
    for lineno, line in enumerate(source.splitlines(), start=1):
        column, open_delimiter = _toml_scan_line(line, open_delimiter)
        if column is not None:
            yield comment_at(lineno, line, column)


def _toml_scan_line(
    line: str, open_delimiter: str | None
) -> tuple[int | None, str | None]:
    """Finds a `#` comment in one TOML line, tracking multi-line strings.

    `open_delimiter`, when set, is the triple-quote delimiter closing an open
    multi-line string; the scan resumes after it closes on this line. Returns
    the comment column (or `None`) and the delimiter still open at the line's
    end (or `None`).
    """
    index = 0
    if open_delimiter is not None:
        close = line.find(open_delimiter)
        if close == -1:
            return None, open_delimiter
        index = close + len(open_delimiter)
    while index < len(line):
        char = line[index]
        if char == "#":
            return index, None
        if char in "\"'":
            triple = line[index : index + 3]
            if triple in ('"""', "'''"):
                close = line.find(triple, index + 3)
                if close == -1:
                    return None, triple
                index = close + 3
                continue
            index = _skip_toml_string(line, index)
            continue
        index += 1
    return None, None


def _skip_toml_string(line: str, index: int) -> int:
    """Returns the index past the single-line string opening at `index`.

    A basic (`"`) string honours backslash escapes; a literal (`'`) string does
    not. An unterminated string consumes the rest of the line, so its content
    is never read as a comment.
    """
    quote = line[index]
    index += 1
    while index < len(line):
        if quote == '"' and line[index] == "\\":
            index += 2
            continue
        if line[index] == quote:
            return index + 1
        index += 1
    return len(line)
