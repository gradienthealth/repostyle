"""Applies safe prose wrapping and spacing fixes."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from repostyle._shared import (
    _join_source_lines,
    _parse_python,
    _walk_tree,
)
from repostyle.languages import COMMENT_SUFFIXES
from repostyle.rules._comment_paragraphs import (
    internal_comment_double_space_faults,
    internal_fill_columns,
    internal_fillable_units,
)
from repostyle.rules._doc_blocks import internal_doc_blocks
from repostyle.rules._fill_units import (
    InternalDOUBLE_SPACE_RE,
    internal_docstring_double_space_faults,
    internal_is_bare_string_literal_statement,
)
from repostyle.rules._reflow import (
    internal_reflow_unit,
    internal_unit_violations,
)
from repostyle.rules._violation import (
    RS_DOUBLE_SPACE_AFTER_PERIOD,
    Violation,
)


def fix_doc_fill(
    path: Path, source: str, skip_lines: frozenset[int] = frozenset()
) -> str:
    """Rewraps docstring and comment paragraphs to their language's column.

    Only a unit `check_doc_fill` reports a finding on is rewritten, so the
    rewrite never reaches prose the rule accepts. Such a unit is greedily
    refilled at its hanging indent; the verbatim structures RS009 exempts (code
    fences, doctests, table and rule lines, preformatted lines, section
    headers) are left untouched, as are units on a line in `skip_lines` and
    units with a backtick span hard-wrapped across source lines. The source's
    line ending is preserved. Docstrings reflow in Python; comments reflow in
    Python, TOML, YAML, and shell alike; YAML folded-scalar prose reflows
    within the scalar's own indent.

    Returns:
        The source with fillable paragraphs rewrapped, unchanged when nothing
        reflows.
    """
    if path.suffix not in COMMENT_SUFFIXES:
        return source
    if path.suffix == ".py" and _parse_python(path, source) is None:
        return source
    source_lines = source.splitlines()
    replacements: list[_Replacement] = []
    columns = internal_fill_columns(path)
    for unit in internal_fillable_units(path, source):
        if any(line.lineno in skip_lines for line in unit):
            continue
        if not any(internal_unit_violations(unit, columns)):
            continue
        rewrapped = internal_reflow_unit(unit, columns)
        if rewrapped is None:
            continue
        start, stop = (unit[0].lineno, unit[-1].lineno)
        if rewrapped == source_lines[start - 1 : stop]:
            continue
        replacements.append((start, stop, rewrapped))
    if not replacements:
        return source
    for start, stop, rewrapped in sorted(replacements, reverse=True):
        source_lines[start - 1 : stop] = rewrapped
    return _join_source_lines(source, source_lines)


_Replacement = tuple[int, int, list[str]]


def check_double_space_after_period(path: Path, source: str) -> Iterator[Violation]:
    """Flags two or more spaces after sentence-ending punctuation.

    A `.`, `!`, or `?` followed by two or more spaces is the old typewriter
    convention. The check reads every comment, every Python string-literal
    statement, and the prose of every Javadoc comment.
    """
    if path.suffix not in COMMENT_SUFFIXES:
        return
    tree = _parse_python(path, source)
    if path.suffix == ".py" and tree is None:
        return
    source_lines = source.splitlines()
    yield from internal_docstring_double_space_faults(tree, source_lines)
    for lineno, start in _javadoc_double_spaces(path, source):
        yield Violation(
            lineno,
            start + 1,
            RS_DOUBLE_SPACE_AFTER_PERIOD,
            "double space after sentence-ending punctuation; use a single space",
        )
    yield from internal_comment_double_space_faults(path, source)


def fix_double_space_in_docstrings(
    path: Path, source: str, skip_lines: frozenset[int] = frozenset()
) -> str:
    """Collapses each flagged double space outside comments, RS061's doc fix.

    A Python string-literal statement and the prose of a Javadoc comment are
    rewritten; comments have a fixer of their own.

    Returns:
        The source with each such space collapsed, unchanged when nothing
        matches.
    """
    source_lines = source.splitlines()
    linenos = [
        lineno
        for lineno in _docstring_linenos(path, source)
        if lineno not in skip_lines
    ]
    changed = False
    for lineno in linenos:
        line = source_lines[lineno - 1]
        fixed = InternalDOUBLE_SPACE_RE.sub("\\1 ", line)
        if fixed != line:
            source_lines[lineno - 1] = fixed
            changed = True
    for lineno, start in sorted(_javadoc_double_spaces(path, source), reverse=True):
        if lineno in skip_lines:
            continue
        line = source_lines[lineno - 1]
        tail = InternalDOUBLE_SPACE_RE.sub("\\1 ", line[start:], count=1)
        source_lines[lineno - 1] = line[:start] + tail
        changed = True
    if not changed:
        return source
    return _join_source_lines(source, source_lines)


def _docstring_linenos(path: Path, source: str) -> Iterator[int]:
    """Yields every line a Python string-literal statement occupies."""
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in _walk_tree(tree):
        if not internal_is_bare_string_literal_statement(node):
            continue
        start = node.value.lineno
        yield from range(start, (node.value.end_lineno or start) + 1)


def _javadoc_double_spaces(path: Path, source: str) -> Iterator[tuple[int, int]]:
    """Yields `(lineno, column)` of each double space in Javadoc prose.

    The match is made on the source line and kept only where the blanked prose
    line agrees with it, so the spaces a blanked `{@code}` tag or `*/` closer
    leaves behind never read as a second space.
    """
    source_lines = source.splitlines()
    for lineno, prose in _javadoc_scan_lines(path, source):
        line = source_lines[lineno - 1]
        for match in InternalDOUBLE_SPACE_RE.finditer(line):
            if prose[match.start() : match.end()] == match.group():
                yield lineno, match.start()


def _javadoc_scan_lines(path: Path, source: str) -> Iterator[tuple[int, str]]:
    """Yields each blanked Javadoc prose line, none for a non-Java file."""
    for block in internal_doc_blocks(path, source):
        if block.is_javadoc:
            yield from block.scan_lines
