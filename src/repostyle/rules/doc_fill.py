"""Paragraph-fill and summary-overflow rules for docstrings and comments."""

from __future__ import annotations

import ast
import itertools
import re
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

from repostyle._comments import COMMENT_SUFFIXES, extract_comments
from repostyle._shared import (
    _BULLET_PATTERN,
    _VERBATIM_LINE_PATTERN,
    _join_source_lines,
    _parse_python,
)
from repostyle.rules._violation import RS_DOC_FILL, RS_DOC_SUMMARY_OVERFLOW, Violation

DOC_FILL_COLUMNS = 79

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
_COMMENT_DIRECTIVE_PATTERN = re.compile(
    r"^#+\s*(!|noqa\b|nosec\b|type:|ruff:|pragma\b|codespell:)"
)


def check_doc_fill(path: Path, source: str) -> Iterator[Violation]:
    """Docstring and comment paragraphs must fill to 79 columns.

    A paragraph line may not end while the next line's first word still fits
    within the limit, and may not run past the limit while a break is
    available. A backtick `...` span is one unbreakable token, so a space
    inside it is not an available break, as with a URL. Summary lines,
    single-line docstrings, section headers, label lines, code fences, doctest
    lines, comment directives, and lines carrying URLs are exempt, as is a unit
    with a backtick span hard-wrapped across lines; bullets and section entries
    wrap as hanging paragraphs. Docstrings are read from Python only; comments
    are read from Python, TOML, YAML, and shell alike.
    """
    if path.suffix not in COMMENT_SUFFIXES:
        return
    # An unparseable Python file is one `fix_doc_fill` declines to rewrite, so
    # the check skips it too rather than flag what `--fix` will not repair.
    if path.suffix == ".py" and _parse_python(path, source) is None:
        return
    for unit in _fillable_units(path, source):
        # A span broken across source lines lost the whitespace at the break,
        # so `_reflow_unit` cannot rejoin it and skips it. The check must
        # exempt the same units, or it would flag what `--fix` will not repair.
        if _span_crosses_line(unit):
            continue
        yield from _unit_violations(unit)


def check_doc_summary_overflow(path: Path, source: str) -> Iterator[Violation]:
    """Flags a docstring summary line that overflows 79 columns.

    PEP 257 and Google style require a docstring's summary to be exactly one
    physical line, so unlike a body paragraph it has no second line to spread
    overflow onto: `check_doc_fill` excludes it for exactly that reason, and
    this rule covers the line `check_doc_fill` leaves out -- the whole line of
    a single-line docstring, or the opening line of a multi-line one. There is
    no mechanical fix; the summary must be shortened by hand.
    """
    if path.suffix != ".py":
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    source_lines = source.splitlines()
    for node in ast.walk(tree):
        if not _is_bare_string_literal_statement(node):
            continue
        lineno = node.value.lineno
        rendered = source_lines[lineno - 1].rstrip()
        if len(rendered) <= DOC_FILL_COLUMNS:
            continue
        indent = len(rendered) - len(rendered.lstrip())
        yield Violation(
            lineno,
            indent + 1,
            RS_DOC_SUMMARY_OVERFLOW,
            f"docstring summary line exceeds {DOC_FILL_COLUMNS} columns; "
            "shorten it by hand, since a one-line summary cannot be rewrapped",
        )


# A pending reflow edit: `(start_lineno, stop_lineno, rewrapped_lines)`
_Replacement = tuple[int, int, list[str]]


def fix_doc_fill(
    path: Path, source: str, skip_lines: frozenset[int] = frozenset()
) -> str:
    """Rewraps docstring and comment paragraphs in `source` to 79 columns.

    Each fillable unit is greedily refilled at its hanging indent; the verbatim
    structures RS009 exempts (code fences, doctests, table and rule lines,
    section headers) are left untouched, as are units on a line in `skip_lines`
    and units with a backtick span hard-wrapped across source lines. The
    source's line ending is preserved. Docstrings reflow in Python; comments
    reflow in Python, TOML, YAML, and shell alike.

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
    for unit in _fillable_units(path, source):
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
    return _join_source_lines(source, source_lines)


def _fillable_units(path: Path, source: str) -> Iterator[list[_FillLine]]:
    """Yields every fillable docstring and comment unit in `source`.

    Both the check and the reflow consume this, so they agree on which
    docstrings and comments are in scope. A Python file contributes docstrings
    and comments; a TOML or YAML file contributes comments alone.
    """
    source_lines = source.splitlines()
    tree = _parse_python(path, source)
    if tree is not None:
        for node in ast.walk(tree):
            if _is_bare_string_literal_statement(node):
                end = node.value.end_lineno
                if end is None or end == node.value.lineno:
                    continue
                yield from _group_paragraphs(
                    _docstring_fill_lines(source_lines, node.value.lineno, end)
                )
    for block in _comment_blocks(path, source, source_lines):
        yield from _group_paragraphs(block)


def _comment_blocks(
    path: Path, source: str, source_lines: list[str]
) -> Iterator[list[_FillLine]]:
    """Yields runs of adjacent own-line comments at the same column.

    A directive comment, or a gap in line or column, closes the open run and
    starts a new one.
    """
    block: list[_FillLine] = []
    previous: tuple[int, int] | None = None
    for comment in extract_comments(path, source):
        if comment.is_trailing:
            continue
        lineno, column = comment.lineno, comment.column
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
        block.append(_FillLine(lineno, rendered, len(rendered) - len(text), text))
        previous = (lineno, column)
    if block:
        yield block


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


def _is_bare_string_literal_statement(node: ast.AST) -> bool:
    """Reports whether `node` is a bare string-literal expression statement."""
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


class _FillLine(NamedTuple):
    lineno: int
    rendered: str
    indent: int
    text: str


def _group_paragraphs(lines: list[_FillLine]) -> Iterator[list[_FillLine]]:
    accumulator = _ParagraphGrouper()
    for line in lines:
        accumulator.consume(line)
    accumulator.close()
    yield from accumulator.units


class _ParagraphGrouper:
    """Groups docstring or comment lines into fillable paragraph units.

    Feed lines in order with `consume`, call `close` after the last line, then
    read the gathered paragraphs from `units`. A verbatim or blank line closes
    the open unit without joining it; a marker line starts a fresh hanging
    paragraph; a plain line either continues the open unit at its established
    indent or starts its own.
    """

    def __init__(self) -> None:
        self.units: list[list[_FillLine]] = []
        self._unit: list[_FillLine] = []
        self._first_indent = 0
        self._cont_indent: int | None = None
        self._in_fence = False
        self._section_indent: int | None = None
        self._entry_indent: int | None = None

    def close(self) -> None:
        """Finishes the open unit, appending it to `units` if non-empty."""
        if self._unit:
            self.units.append(self._unit)
        self._unit = []
        self._cont_indent = None

    def consume(self, line: _FillLine) -> None:
        """Routes `line` to its handler, ending the open unit as needed."""
        if self._consume_verbatim(line):
            return
        self._exit_finished_section(line)
        if self._consume_marker(line):
            return
        self._consume_paragraph(line)

    def _consume_marker(self, line: _FillLine) -> bool:
        """Opens a fresh unit for a header, entry, bullet, or label line.

        A section header opens a new section and is not itself filled. A
        section entry, bullet, or label line starts a hanging paragraph.
        Returns whether `line` was a marker and has been handled.
        """
        if line.text in _SECTION_HEADERS:
            self.close()
            self._section_indent = line.indent
            self._entry_indent = None
            return True
        if (
            self._starts_entry(line)
            or _BULLET_PATTERN.match(line.text)
            or _LABEL_LINE_PATTERN.match(line.text)
        ):
            self.close()
            self._unit = [line]
            self._first_indent = line.indent
            return True
        return False

    def _consume_paragraph(self, line: _FillLine) -> None:
        """Appends `line` to the open unit or starts a unit with it.

        A line indented past a one-line unit sets that unit's continuation
        indent; otherwise a line matching the established indent continues the
        unit. Any other line opens its own unit.
        """
        if self._unit and self._extend_open_unit(line):
            return
        self._unit = [line]
        self._first_indent = line.indent

    def _consume_verbatim(self, line: _FillLine) -> bool:
        """Closes the unit and reports whether `line` is unfillable.

        Blank lines, code fences, doctests, and table or rule lines are
        verbatim: they never join a paragraph. A fence line also toggles
        whether subsequent lines sit inside a fenced block.
        """
        if not line.text:
            self.close()
            return True
        if line.text.startswith("```"):
            self.close()
            self._in_fence = not self._in_fence
            return True
        if self._in_fence or line.text.startswith((">>>", "... ")):
            self.close()
            return True
        if _VERBATIM_LINE_PATTERN.match(line.text):
            self.close()
            return True
        return False

    def _exit_finished_section(self, line: _FillLine) -> None:
        """Clears section tracking when `line` falls back to its margin."""
        if self._section_indent is not None and line.indent <= self._section_indent:
            self._section_indent = None
            self._entry_indent = None

    def _extend_open_unit(self, line: _FillLine) -> bool:
        """Appends `line` to the open unit when its indent fits, else ends it.

        Returns whether `line` joined the open unit.
        """
        if len(self._unit) == 1 and line.indent > self._first_indent:
            self._cont_indent = line.indent
            self._unit.append(line)
            return True
        expected = (
            self._first_indent if self._cont_indent is None else self._cont_indent
        )
        if line.indent == expected:
            self._unit.append(line)
            return True
        self.close()
        return False

    def _starts_entry(self, line: _FillLine) -> bool:
        """Reports whether `line` begins an entry within the open section.

        Latches the section's entry indent to the first line examined, so later
        lines count as entries only when they align with it.
        """
        if self._section_indent is None:
            return False
        if self._entry_indent is None:
            self._entry_indent = line.indent
        return (
            line.indent == self._entry_indent
            and _SECTION_ENTRY_PATTERN.match(line.text) is not None
        )


def _unit_violations(unit: list[_FillLine]) -> Iterator[Violation]:
    for line, following in itertools.pairwise(unit):
        first_word = _atomic_tokens(following.text)[0]
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


def _has_break_before_limit(line: _FillLine) -> bool:
    """Reports whether a legal wrap break falls within the column limit.

    A space inside a backtick `...` span is not a legal break, as with a URL,
    so a line may pass the limit without one. Backticks that do not pair up
    cannot delimit a span, so every space then counts.
    """
    prefix_length = len(line.rendered) - len(line.text)
    backticks_paired = line.rendered.count("`") % 2 == 0
    in_span = False
    for index, char in enumerate(line.rendered[: DOC_FILL_COLUMNS + 1]):
        if char == "`" and backticks_paired:
            in_span = not in_span
        elif char == " " and not in_span and index > prefix_length:
            return True
    return False


def _reflow_unit(unit: list[_FillLine]) -> list[str] | None:
    """Returns `unit` rewrapped to the column limit, or `None` to skip it.

    A unit whose text contains a triple quote is skipped, since rewrapping
    would move the quote. A unit with a backtick span hard-wrapped across
    source lines is skipped too, since rejoining it would have to invent the
    whitespace the break elided. The first line keeps the unit's leading
    whitespace and any marker; continuation lines wrap to the hanging indent.
    """
    if any('"""' in line.text or "'''" in line.text for line in unit):
        return None
    if _span_crosses_line(unit):
        return None
    first_indent = unit[0].indent
    lead = unit[0].rendered[:first_indent]
    cont = lead + " " * (_hanging_indent(unit) - first_indent)
    words = _atomic_tokens(" ".join(line.text for line in unit))
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


def _atomic_tokens(text: str) -> list[str]:
    """Splits `text` into fill tokens, keeping each backtick span whole.

    Whitespace splits `text` into tokens, except inside a backtick `...` span,
    where spaces are kept so the span stays one unbreakable token the way a URL
    does. Backticks that do not pair up cannot delimit a span, so `text` then
    splits on whitespace alone.
    """
    if text.count("`") % 2:
        return text.split()
    tokens: list[str] = []
    current = ""
    in_span = False
    for char in text:
        if char == "`":
            in_span = not in_span
            current += char
        elif char.isspace() and not in_span:
            if current:
                tokens.append(current)
                current = ""
        else:
            current += char
    if current:
        tokens.append(current)
    return tokens


def _hanging_indent(unit: list[_FillLine]) -> int:
    """Returns the indent continuation lines of `unit` wrap to.

    An established continuation indent (a unit already spanning lines) is
    reused. A single over-long line wraps under its own marker: two columns for
    a bullet, four for a section entry or label, and back to the same indent
    for a plain paragraph.
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


def _span_crosses_line(unit: list[_FillLine]) -> bool:
    """Reports whether a backtick span in `unit` crosses a line."""
    open_span = False
    for line in unit[:-1]:
        open_span ^= line.text.count("`") % 2 == 1
        if open_span:
            return True
    return False
