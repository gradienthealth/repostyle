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

from pystyle.rules._shared import _parse_python
from pystyle.rules._violation import RS_DOC_FILL, Violation

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
# A markdown table row (`|...|`) or a line made only of pipe, dash,
# plus, and equals characters (`+----+`, `====`, a `---` rule) opens
# content whose alignment is meaningful, so it is verbatim: never filled
# and never reflowed. Requiring the whole line to be those characters
# keeps flag-like prose (`--fix ...`) and bullets (`- `) from matching.
_VERBATIM_LINE_PATTERN = re.compile(r"^\||^[-+=][-+=|\s]*$")


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
        if _VERBATIM_LINE_PATTERN.match(line.text):
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


def _unit_violations(unit: list[_FillLine]) -> Iterator[Violation]:
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


def _fillable_units(source: str, tree: ast.AST) -> Iterator[list[_FillLine]]:
    """Yield every fillable docstring and comment unit in `source`.

    Both the check and the reflow consume this, so they agree on which
    docstrings and comments are in scope.
    """
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
            yield from _fill_units(
                _docstring_fill_lines(source_lines, node.value.lineno, end)
            )
    for block in _comment_blocks(source):
        yield from _fill_units(block)


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
    for unit in _fillable_units(source, tree):
        yield from _unit_violations(unit)


def _hanging_indent(unit: list[_FillLine]) -> int:
    """Return the indent continuation lines of `unit` wrap to.

    An established continuation indent (a unit already spanning lines)
    is reused. A single over-long line wraps under its own marker: two
    columns for a bullet, four for a section entry or label, and back to
    the same indent for a plain paragraph.
    """
    first_indent = unit[0].indent
    if len(unit) > 1:
        return unit[1].indent
    text = unit[0].text
    if _BULLET_PATTERN.match(text):
        return first_indent + 2
    if _SECTION_ENTRY_PATTERN.match(text) or _LABEL_LINE_PATTERN.match(text):
        return first_indent + 4
    return first_indent


def _reflow_unit(unit: list[_FillLine]) -> list[str] | None:
    """Return `unit` rewrapped to the column limit, or `None` to skip it.

    A unit whose text contains a triple quote is skipped, since
    rewrapping would move the quote. The first line keeps the unit's
    leading whitespace and any marker; continuation lines wrap to the
    hanging indent.
    """
    if any('"""' in line.text or "'''" in line.text for line in unit):
        return None
    first_indent = unit[0].indent
    lead = unit[0].rendered[:first_indent]
    cont = lead + " " * (_hanging_indent(unit) - first_indent)
    words = " ".join(line.text for line in unit).split()
    lines: list[str] = []
    current = lead + words[0]
    for word in words[1:]:
        if len(current) + 1 + len(word) <= DOC_FILL_COLUMNS:
            current = f"{current} {word}"
        else:
            lines.append(current)
            current = cont + word
    lines.append(current)
    return lines


def reflow_doc_fill(
    path: Path, source: str, skip_lines: frozenset[int] = frozenset()
) -> str:
    """Rewrap docstring and comment paragraphs in `source` to 72 columns.

    Each fillable unit is greedily refilled at its hanging indent; the
    verbatim structures RS009 exempts (code fences, doctests, table and
    rule lines, section headers) are left untouched, as are units on a
    line in `skip_lines`. The source's line ending is preserved. Return
    the source unchanged when nothing reflows.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return source
    source_lines = source.splitlines()
    replacements: list[tuple[int, int, list[str]]] = []
    for unit in _fillable_units(source, tree):
        if any(line.lineno in skip_lines for line in unit):
            continue
        rewrapped = _reflow_unit(unit)
        if rewrapped is None:
            continue
        start, stop = unit[0].lineno, unit[-1].lineno
        if rewrapped == source_lines[start - 1 : stop]:
            continue
        replacements.append((start, stop, rewrapped))
    if not replacements:
        return source
    for start, stop, rewrapped in sorted(replacements, reverse=True):
        source_lines[start - 1 : stop] = rewrapped
    newline = "\r\n" if "\r\n" in source else "\n"
    rewritten = newline.join(source_lines)
    return rewritten + newline if source.endswith("\n") else rewritten
