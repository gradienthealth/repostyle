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


def check_doc_fill(path: Path, source: str) -> Iterator[Violation]:
    """Docstring and comment paragraphs must fill to 72 columns.

    A paragraph line may not end while the next line's first word still
    fits within the limit, and may not run past the limit while a break
    is available. A backtick `...` span is one unbreakable token, so a
    space inside it is not an available break, as with a URL. Summary
    lines, single-line docstrings, section headers, label lines, code
    fences, doctest lines, comment directives, and lines carrying URLs
    are exempt; bullets and section entries wrap as hanging paragraphs.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    for unit in _fillable_units(source, tree):
        yield from _unit_violations(unit)


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


class _FillLine(NamedTuple):
    lineno: int
    rendered: str
    indent: int
    text: str


def _fill_units(lines: list[_FillLine]) -> Iterator[list[_FillLine]]:
    accumulator = _UnitAccumulator()
    for line in lines:
        accumulator.consume(line)
    accumulator.close()
    yield from accumulator.units


class _UnitAccumulator:
    """Group docstring or comment lines into fillable paragraph units.

    Feed lines in order with `consume`, call `close` after the last
    line, then read the gathered paragraphs from `units`. A verbatim or
    blank line closes the open unit without joining it; a marker line
    starts a fresh hanging paragraph; a plain line either continues the
    open unit at its established indent or starts its own.
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
        """Finish the open unit, appending it to `units` if non-empty."""
        if self._unit:
            self.units.append(self._unit)
        self._unit = []
        self._cont_indent = None

    def consume(self, line: _FillLine) -> None:
        """Route `line` to its handler, ending the open unit as needed."""
        if self._consume_verbatim(line):
            return
        self._exit_finished_section(line)
        if self._consume_marker(line):
            return
        self._consume_paragraph(line)

    def _consume_marker(self, line: _FillLine) -> bool:
        """Open a fresh unit for a header, entry, bullet, or label line.

        A section header opens a new section and is not itself filled. A
        section entry, bullet, or label line starts a hanging paragraph.
        Return whether `line` was a marker and has been handled.
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
        """Append `line` to the open unit or start a unit with it.

        A line indented past a one-line unit sets that unit's
        continuation indent; otherwise a line matching the established
        indent continues the unit. Any other line opens its own unit.
        """
        if self._unit and self._extend_open_unit(line):
            return
        self._unit = [line]
        self._first_indent = line.indent

    def _consume_verbatim(self, line: _FillLine) -> bool:
        """Close the unit and report whether `line` is unfillable.

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
        """Clear section tracking when `line` falls back to its margin."""
        if self._section_indent is not None and line.indent <= self._section_indent:
            self._section_indent = None
            self._entry_indent = None

    def _extend_open_unit(self, line: _FillLine) -> bool:
        """Append `line` to the open unit when its indent fits, else end it.

        Return whether `line` joined the open unit.
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
        """Report whether `line` begins an entry within the open section.

        Latch the section's entry indent to the first line examined, so
        later lines count as entries only when they align with it.
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
    """Report whether a legal wrap break falls within the column limit.

    A space inside a backtick `...` span is not a legal break, as with a
    URL, so a line may pass the limit without one. Backticks that do not
    pair up cannot delimit a span, so every space then counts.
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
    """Split `text` into fill tokens, keeping each backtick span whole.

    Whitespace splits `text` into tokens, except inside a backtick `...`
    span, where spaces are kept so the span stays one unbreakable token
    the way a URL does. Backticks that do not pair up cannot delimit a
    span, so `text` then splits on whitespace alone.
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
