"""Internal doc-fill implementation partition 3."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from repostyle._comments import COMMENT_SUFFIXES, extract_comments, extract_folded_runs
from repostyle._shared import (
    _join_source_lines,
    _parse_python,
    _walk_tree,
)
from repostyle.rules._doc_fill_impl_4 import (
    InternalDOUBLE_SPACE_RE,
    internal_docstring_fill_lines,
    internal_folded_fill_lines,
    internal_group_paragraphs,
    internal_is_bare_string_literal_statement,
    internal_is_folded_prose,
)
from repostyle.rules._doc_fill_impl_7 import (
    InternalFillLine,
)
from repostyle.rules._violation import (
    RS_DOUBLE_SPACE_AFTER_PERIOD,
    Violation,
)


def fix_double_space_in_comments(
    path: Path, source: str, skip_lines: frozenset[int] = frozenset()
) -> str:
    """Collapses sentence-ending double spaces in comments.

    Returns:
        The source with double spaces collapsed, unchanged when nothing
        matches.
    """
    if path.suffix not in COMMENT_SUFFIXES:
        return source
    source_lines = source.splitlines()
    changed = False
    for comment in extract_comments(path, source):
        if comment.lineno in skip_lines:
            continue
        line = source_lines[comment.lineno - 1]
        col = comment.column
        comment_part = line[col:]
        fixed_comment = InternalDOUBLE_SPACE_RE.sub("\\1 ", comment_part)
        if fixed_comment != comment_part:
            source_lines[comment.lineno - 1] = line[:col] + fixed_comment
            changed = True
    if not changed:
        return source
    return _join_source_lines(source, source_lines)


def internal_fillable_units(
    path: Path, source: str
) -> Iterator[list[InternalFillLine]]:
    """Yields every fillable docstring, comment, and YAML prose unit.

    Both the check and the reflow consume this, so they agree on what is in
    scope. A Python file contributes docstrings and comments; a TOML or shell
    file comments alone; a YAML file its comments and the prose inside its
    folded block scalars.
    """
    source_lines = source.splitlines()
    tree = _parse_python(path, source)
    if tree is not None:
        for node in _walk_tree(tree):
            if internal_is_bare_string_literal_statement(node):
                end = node.value.end_lineno
                if end is None or end == node.value.lineno:
                    continue
                yield from internal_group_paragraphs(
                    internal_docstring_fill_lines(source_lines, node.value.lineno, end)
                )
    for block in _comment_blocks(path, source, source_lines):
        yield from internal_group_paragraphs(block)
    for run in extract_folded_runs(path, source):
        lines = internal_folded_fill_lines(source_lines, run)
        if internal_is_folded_prose(lines):
            yield from internal_group_paragraphs(lines)


def _comment_blocks(
    path: Path, source: str, source_lines: list[str]
) -> Iterator[list[InternalFillLine]]:
    """Yields runs of adjacent own-line comments at the same column.

    A directive comment, or a gap in line or column, closes the open run and
    starts a new one.
    """
    block: list[InternalFillLine] = []
    previous: tuple[int, int] | None = None
    for comment in extract_comments(path, source):
        if comment.is_trailing:
            continue
        lineno, column = (comment.lineno, comment.column)
        if _COMMENT_DIRECTIVE_PATTERN.match(comment.string):
            if block:
                yield block
            block = []
            previous = None
            continue
        if previous != (lineno - 1, column) and block:
            yield block
            block = []
        rendered = source_lines[lineno - 1].rstrip()
        text = comment.string.lstrip("#").strip()
        block.append(
            InternalFillLine(lineno, rendered, len(rendered) - len(text), text)
        )
        previous = (lineno, column)
    if block:
        yield block


_COMMENT_DIRECTIVE_PATTERN = re.compile(
    "^#+\\s*(!|noqa\\b|nosec\\b|type:|ruff:|pragma\\b|codespell:)"
)


def internal_comment_double_space_faults(
    path: Path, source: str
) -> Iterator[Violation]:
    """Yields double-space violations from comment lines."""
    for comment in extract_comments(path, source):
        for match in InternalDOUBLE_SPACE_RE.finditer(comment.string):
            yield Violation(
                comment.lineno,
                comment.column + match.start() + 1,
                RS_DOUBLE_SPACE_AFTER_PERIOD,
                "double space after sentence-ending punctuation; use a single space",
            )
