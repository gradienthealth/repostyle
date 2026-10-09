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
    internal_fillable_units,
)
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
    Violation,
)


def fix_doc_fill(
    path: Path, source: str, skip_lines: frozenset[int] = frozenset()
) -> str:
    """Rewraps docstring and comment paragraphs in `source` to 79 columns.

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
    for unit in internal_fillable_units(path, source):
        if any(line.lineno in skip_lines for line in unit):
            continue
        if not any(internal_unit_violations(unit)):
            continue
        rewrapped = internal_reflow_unit(unit)
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

    A `.`, `!`, or `?` followed by two or more spaces in a docstring or comment
    is the old typewriter convention. Docstrings are checked in Python only;
    comments in Python, TOML, YAML, and shell alike.
    """
    if path.suffix not in COMMENT_SUFFIXES:
        return
    tree = _parse_python(path, source)
    if path.suffix == ".py" and tree is None:
        return
    source_lines = source.splitlines()
    yield from internal_docstring_double_space_faults(tree, source_lines)
    yield from internal_comment_double_space_faults(path, source)


def fix_double_space_in_docstrings(
    path: Path, source: str, skip_lines: frozenset[int] = frozenset()
) -> str:
    """Collapses sentence-ending double spaces in Python docstrings.

    Returns:
        The source with double spaces collapsed, unchanged when nothing matches
        or the file is not Python.
    """
    if path.suffix != ".py":
        return source
    tree = _parse_python(path, source)
    if tree is None:
        return source
    source_lines = source.splitlines()
    changed = False
    for node in _walk_tree(tree):
        if not internal_is_bare_string_literal_statement(node):
            continue
        start = node.value.lineno
        end = node.value.end_lineno or start
        for lineno in range(start, end + 1):
            if lineno in skip_lines:
                continue
            line = source_lines[lineno - 1]
            fixed = InternalDOUBLE_SPACE_RE.sub("\\1 ", line)
            if fixed != line:
                source_lines[lineno - 1] = fixed
                changed = True
    if not changed:
        return source
    return _join_source_lines(source, source_lines)
