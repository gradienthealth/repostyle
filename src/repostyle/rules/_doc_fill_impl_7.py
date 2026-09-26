"""Internal doc-fill implementation partition 7."""

from __future__ import annotations

import re
from typing import NamedTuple

from repostyle._shared import (
    _BULLET_PATTERN,
)


def internal_atomic_tokens(text: str) -> list[str]:
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
        elif char.isspace() and (not in_span):
            if current:
                tokens.append(current)
                current = ""
        else:
            current += char
    if current:
        tokens.append(current)
    return tokens


def internal_display_width(text: str) -> int:
    """Returns the columns `text` occupies, counting a tab to its next stop.

    Args:
        text: A complete rendered line.

    Returns:
        The number of rendered columns.
    """
    return len(internal_expand_tabs(text))


def internal_expand_tabs(text: str) -> str:
    """Replaces each tab in `text` with spaces up to its next tab stop."""
    return text.expandtabs(_TAB_STOP)


_TAB_STOP = 8


def internal_hanging_indent(unit: list[InternalFillLine]) -> int:
    """Returns the indent continuation lines of `unit` wrap to.

    An established continuation indent (a unit already spanning lines) is
    reused. A single over-long line wraps under its own marker: two columns for
    a bullet, four for a section entry or label, and back to the same indent
    for a plain paragraph or any line of a YAML folded scalar.
    """
    first_indent = unit[0].indent
    if len(unit) > 1:
        return unit[1].indent
    if unit[0].is_folded:
        return first_indent
    text = unit[0].text
    if _BULLET_PATTERN.match(text):
        return first_indent + 2
    if InternalSECTION_ENTRY_PATTERN.match(text) or InternalLABEL_LINE_PATTERN.match(
        text
    ):
        return first_indent + 4
    return first_indent


InternalLABEL_LINE_PATTERN = re.compile("^[A-Z][A-Za-z]*([ -][A-Z][A-Za-z]*)*:(\\s|$)")

InternalSECTION_ENTRY_PATTERN = re.compile("^\\S+:(\\s|$)")


def internal_holds_triple_quote(unit: list[InternalFillLine]) -> bool:
    """Reports whether any line of `unit` carries a triple quote."""
    return any('"""' in line.text or "'''" in line.text for line in unit)


def internal_span_crosses_line(unit: list[InternalFillLine]) -> bool:
    """Reports whether a backtick span in `unit` crosses a line."""
    open_span = False
    for line in unit[:-1]:
        open_span ^= line.text.count("`") % 2 == 1
        if open_span:
            return True
    return False


class InternalFillLine(NamedTuple):
    lineno: int
    rendered: str
    indent: int
    text: str
    is_folded: bool = False
