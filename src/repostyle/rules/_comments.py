"""The cross-language `#`-comment extractor shared by the comment rules.

RS009 (paragraph wrapping), RS030 (terminal punctuation), and the
suppression parser each read `#` comments from Python, TOML, and YAML.
This module holds the one extractor they share: Python through the
tokenizer, TOML and YAML through a string- and block-aware line scan.
"""

from __future__ import annotations

import io
import re
import tokenize
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

# A YAML block scalar introducer: a value that, after a `:` or `-` lead
# or standing at the line start, is a `|` or `>` carrying only chomping
# and indent indicators, so the indented lines that follow are literal.
_BLOCK_SCALAR_PATTERN = re.compile(r"(?:[:-]\s+|^\s*)[|>][0-9+-]*\s*$")

# The file types whose `#` comments the comment rules read. Python is
# tokenized; TOML and YAML are scanned line by line. A type absent here
# is never comment-checked.
COMMENT_SUFFIXES = frozenset({".py", ".toml", ".yaml", ".yml"})


class _CommentToken(NamedTuple):
    lineno: int
    """1-based line the comment starts on."""
    column: int
    """0-based column of the leading hash."""
    string: str
    """The comment from its leading hash to the end of the line."""
    is_trailing: bool
    """Whether code or data precedes the comment on its line."""


def extract_comments(path: Path, source: str) -> Iterator[_CommentToken]:
    """Yield each `#` comment in `source`, dispatched by file type.

    A Python file is tokenized. A TOML or YAML file is scanned line by
    line under that language's string and block rules, so a `#` inside a
    string, a TOML multi-line string, or a YAML block scalar is not
    mistaken for a comment. A file of any other type yields nothing. The
    scan is conservative: an unrecognised construct keeps its `#` out of
    the results rather than risk flagging string content.
    """
    suffix = path.suffix
    if suffix == ".py":
        yield from _python_comments(source)
    elif suffix in {".toml", ".yaml", ".yml"}:
        yield from _hash_comments(source, is_yaml=suffix != ".toml")


def _hash_comments(source: str, *, is_yaml: bool) -> Iterator[_CommentToken]:
    """Yield each `#` comment in TOML or YAML `source`, line by line.

    Dispatch each line to the language's scanner, carrying the
    cross-line state a `#` scan needs: the delimiter awaited inside an
    open TOML multi-line string, and the introducer indent of an open
    YAML block scalar. A line consumed by either of those carries no
    comment.
    """
    awaiting: str | None = None
    block_indent: int | None = None
    for lineno, line in enumerate(source.splitlines(), start=1):
        if is_yaml:
            if block_indent is not None and _inside_block(line, block_indent):
                continue
            block_indent = None
            column = _yaml_comment_column(line)
            content = line if column is None else line[:column]
            if _opens_block_scalar(content):
                block_indent = _indent_of(line)
        else:
            column, awaiting = _toml_scan_line(line, awaiting)
        if column is not None:
            yield _CommentToken(
                lineno, column, line[column:], bool(line[:column].strip())
            )


def _inside_block(line: str, block_indent: int) -> bool:
    """Report whether `line` is content of a block scalar at `block_indent`."""
    return not line.strip() or _indent_of(line) > block_indent


def _indent_of(line: str) -> int:
    """Return the count of leading spaces on `line`."""
    return len(line) - len(line.lstrip(" "))


def _opens_block_scalar(content: str) -> bool:
    """Report whether a YAML line opens a `|` or `>` block scalar.

    The value, after a `:` or `-` lead or standing alone, is a `|` or
    `>` with optional chomping (`+`/`-`) and indent (a digit) indicators
    and nothing else, so the indented lines that follow are literal
    content.
    """
    return _BLOCK_SCALAR_PATTERN.search(content) is not None


def _python_comments(source: str) -> Iterator[_CommentToken]:
    """Yield each comment token in Python `source` via the tokenizer.

    Tokens are yielded as the tokenizer produces them, so a `TokenError`
    on an unterminated tail still surfaces the comments before it.
    """
    source_lines = source.splitlines()
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type != tokenize.COMMENT:
                continue
            lineno, column = token.start
            is_trailing = bool(source_lines[lineno - 1][:column].strip())
            yield _CommentToken(lineno, column, token.string, is_trailing)
    except (tokenize.TokenError, SyntaxError):
        # An unterminated tail raises TokenError; inconsistent
        # indentation raises IndentationError/TabError (SyntaxError
        # subclasses). Stop at the fault and keep the comments already
        # surfaced.
        return


def _toml_scan_line(line: str, awaiting: str | None) -> tuple[int | None, str | None]:
    """Find a `#` comment in one TOML line, tracking multi-line strings.

    `awaiting`, when set, is the triple-quote delimiter closing an open
    multi-line string; the scan resumes after it closes on this line.
    Return the comment column (or `None`) and the delimiter still open
    at the line's end (or `None`).
    """
    index = 0
    if awaiting is not None:
        close = line.find(awaiting)
        if close == -1:
            return None, awaiting
        index = close + len(awaiting)
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
    """Return the index past the single-line string opening at `index`.

    A basic (`"`) string honours backslash escapes; a literal (`'`)
    string does not. An unterminated string consumes the rest of the
    line, so its content is never read as a comment.
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


def _yaml_comment_column(line: str) -> int | None:
    """Return the column of a `#` comment in one YAML line, or `None`.

    A `#` opens a comment only at the line start or after whitespace,
    and never inside a quoted scalar. A double-quoted scalar honours
    backslash escapes; a single-quoted one escapes a quote by doubling
    it.
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
    """Return the index past the double-quoted scalar opening at `index`."""
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
    """Return the index past the single-quoted scalar opening at `index`."""
    index += 1
    while index < len(line):
        if line[index] == "'":
            if line[index + 1 : index + 2] == "'":
                index += 2
                continue
            return index + 1
        index += 1
    return len(line)
