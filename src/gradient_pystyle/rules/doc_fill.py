"""Paragraph-fill rule for docstrings and comments."""

from __future__ import annotations

import ast
import io
import itertools
import re
import tokenize
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

from gradient_pystyle.rules._shared import _parse_python
from gradient_pystyle.rules._violation import RS_DOC_FILL, Violation

DOC_FILL_COLUMNS = 72

_SECTION_HEADERS = frozenset(
    {
        "Args:",
        "Attributes:",
        "Example:",
        "Examples:",
        "Note:",
        "Notes:",
        "Raises:",
        "Returns:",
        "Yields:",
    }
)
_LABEL_LINE_PATTERN = re.compile(r"^[A-Z][A-Za-z]*([ -][A-Z][A-Za-z]*)*:(\s|$)")
_SECTION_ENTRY_PATTERN = re.compile(r"^\S+:(\s|$)")
_BULLET_PATTERN = re.compile(r"^[-*+] ")
_COMMENT_DIRECTIVE_PATTERN = re.compile(r"^#+\s*(!|noqa\b|type:|ruff:|pragma\b)")


class _FillLine(NamedTuple):
    lineno: int
    rendered: str
    indent: int
    text: str


def _docstring_fill_lines(
    source_lines: list[str], start: int, end: int
) -> list[_FillLine]:
    lines: list[_FillLine] = []
    for lineno in range(start + 1, end + 1):
        rendered = source_lines[lineno - 1].rstrip()
        text = rendered.strip()
        if text in ('"""', "'''"):
            continue
        lines.append(_FillLine(lineno, rendered, len(rendered) - len(text), text))
    return lines


def _comment_blocks(source: str) -> Iterator[list[_FillLine]]:
    source_lines = source.splitlines()
    block: list[_FillLine] = []
    previous: tuple[int, int] | None = None
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except tokenize.TokenError:
        return
    for token in tokens:
        if token.type != tokenize.COMMENT:
            continue
        lineno, column = token.start
        if source_lines[lineno - 1][:column].strip():
            continue
        if _COMMENT_DIRECTIVE_PATTERN.match(token.string):
            if block:
                yield block
            block = []
            previous = None
            continue
        if previous != (lineno - 1, column) and block:
            yield block
            block = []
        rendered = source_lines[lineno - 1].rstrip()
        text = token.string.lstrip("#").strip()
        block.append(_FillLine(lineno, rendered, len(rendered) - len(text), text))
        previous = (lineno, column)
    if block:
        yield block


def _fill_units(lines: list[_FillLine]) -> Iterator[list[_FillLine]]:
    unit: list[_FillLine] = []
    first_indent = 0
    cont_indent: int | None = None
    in_fence = False
    section_indent: int | None = None
    entry_indent: int | None = None
    units: list[list[_FillLine]] = []

    def close() -> None:
        nonlocal unit, cont_indent
        if unit:
            units.append(unit)
        unit = []
        cont_indent = None

    for line in lines:
        if not line.text:
            close()
            continue
        if line.text.startswith("```"):
            close()
            in_fence = not in_fence
            continue
        if in_fence or line.text.startswith((">>>", "... ")):
            close()
            continue
        if line.text in _SECTION_HEADERS:
            close()
            section_indent = line.indent
            entry_indent = None
            continue
        if section_indent is not None and line.indent <= section_indent:
            section_indent = None
            entry_indent = None
        starts_entry = False
        if section_indent is not None:
            if entry_indent is None:
                entry_indent = line.indent
            starts_entry = (
                line.indent == entry_indent
                and _SECTION_ENTRY_PATTERN.match(line.text) is not None
            )
        if (
            starts_entry
            or _BULLET_PATTERN.match(line.text)
            or _LABEL_LINE_PATTERN.match(line.text)
        ):
            close()
            unit = [line]
            first_indent = line.indent
            continue
        if unit:
            if len(unit) == 1 and line.indent > first_indent:
                cont_indent = line.indent
                unit.append(line)
                continue
            expected = first_indent if cont_indent is None else cont_indent
            if line.indent == expected:
                unit.append(line)
                continue
            close()
        unit = [line]
        first_indent = line.indent
    close()
    yield from units


def _has_break_before_limit(line: _FillLine) -> bool:
    prefix_length = len(line.rendered) - len(line.text)
    break_at = line.rendered.rfind(" ", prefix_length + 1, DOC_FILL_COLUMNS + 1)
    return break_at != -1


def _fill_violations(lines: list[_FillLine]) -> Iterator[Violation]:
    for unit in _fill_units(lines):
        for line, following in itertools.pairwise(unit):
            first_word = following.text.split()[0]
            if len(line.rendered) + 1 + len(first_word) <= DOC_FILL_COLUMNS:
                yield Violation(
                    line.lineno,
                    line.indent + 1,
                    RS_DOC_FILL,
                    f"under-wrapped line: '{first_word}' still fits within "
                    f"{DOC_FILL_COLUMNS} columns",
                )
        for line in unit:
            if len(line.rendered) <= DOC_FILL_COLUMNS or "://" in line.rendered:
                continue
            if not _has_break_before_limit(line):
                continue
            yield Violation(
                line.lineno,
                line.indent + 1,
                RS_DOC_FILL,
                f"line exceeds {DOC_FILL_COLUMNS} columns; rewrap the paragraph",
            )


def check_doc_fill(path: Path, source: str) -> Iterator[Violation]:
    """Docstring and comment paragraphs must fill to 72 columns.

    A paragraph line may not end while the next line's first word still
    fits within the limit, and may not run past the limit while a break
    is available. Summary lines, single-line docstrings, section
    headers, label lines, code fences, doctest lines, comment
    directives, and lines carrying URLs are exempt; bullets and section
    entries wrap as hanging paragraphs.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    source_lines = source.splitlines()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            end = node.value.end_lineno
            if end is None or end == node.value.lineno:
                continue
            yield from _fill_violations(
                _docstring_fill_lines(source_lines, node.value.lineno, end)
            )
    for block in _comment_blocks(source):
        yield from _fill_violations(block)
