"""Checks and reflows documentation paragraphs."""

from __future__ import annotations

import itertools
import re
from collections.abc import Iterator

from repostyle.rules._display_width import (
    InternalFillLine,
    internal_atomic_tokens,
    internal_display_width,
    internal_expand_tabs,
    internal_hanging_indent,
    internal_holds_triple_quote,
    internal_span_crosses_line,
)
from repostyle.rules._violation import (
    RS_DOC_FILL,
    Violation,
)

InternalSECTION_HEADERS = frozenset(
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

InternalPREFORMATTED_LINE_PATTERN = re.compile("\\\\$|\\S {3,}\\S")


def internal_unit_violations(unit: list[InternalFillLine]) -> Iterator[Violation]:
    """Yields wrapping faults found in one fillable prose unit."""
    for line, following in itertools.pairwise(unit):
        first_word = internal_atomic_tokens(following.text)[0]
        if internal_display_width(f"{line.rendered} {first_word}") <= DOC_FILL_COLUMNS:
            yield Violation(
                line.lineno,
                line.indent + 1,
                RS_DOC_FILL,
                f"under-wrapped line: '{first_word}' still fits within {DOC_FILL_COLUMNS} columns",
            )
    for line in unit:
        if (
            internal_display_width(line.rendered) <= DOC_FILL_COLUMNS
            or "://" in line.rendered
        ):
            continue
        if not _has_break_before_limit(line):
            continue
        yield Violation(
            line.lineno,
            line.indent + 1,
            RS_DOC_FILL,
            f"line exceeds {DOC_FILL_COLUMNS} columns; rewrap the paragraph",
        )


def _has_break_before_limit(line: InternalFillLine) -> bool:
    """Reports whether a legal wrap break falls within the column limit.

    A space inside a backtick `...` span is not a legal break, as with a URL,
    so a line may pass the limit without one. Backticks that do not pair up
    cannot delimit a span, so every space then counts. The line is scanned with
    its tabs expanded, so an index is a column and the break has to fall within
    the limit as a reader sees it.
    """
    expanded = internal_expand_tabs(line.rendered)
    prefix_width = internal_display_width(
        line.rendered[: len(line.rendered) - len(line.text)]
    )
    backticks_paired = line.rendered.count("`") % 2 == 0
    in_span = False
    for index, char in enumerate(expanded[: DOC_FILL_COLUMNS + 1]):
        if char == "`" and backticks_paired:
            in_span = not in_span
        elif char == " " and (not in_span) and (index > prefix_width):
            return True
    return False


def internal_reflow_unit(unit: list[InternalFillLine]) -> list[str] | None:
    """Returns `unit` rewrapped to the column limit, or `None` to skip it.

    A unit whose text contains a triple quote is skipped, since rewrapping
    would move the quote, and one with a backtick span hard-wrapped across
    source lines is skipped too, since rejoining it would have to invent the
    whitespace the break elided. `check_doc_fill` exempts both, so this returns
    `None` only for a unit it raised nothing about. The first line keeps the
    unit's leading whitespace and any marker; continuation lines wrap to the
    hanging indent. Both are emitted with the unit's own indent characters,
    tabs included, but measured at their expanded width, so no returned line
    runs past the limit as a reader sees it.
    """
    if internal_holds_triple_quote(unit) or internal_span_crosses_line(unit):
        return None
    first_indent = unit[0].indent
    lead = unit[0].rendered[:first_indent]
    cont = lead + " " * (internal_hanging_indent(unit) - first_indent)
    words = internal_atomic_tokens(" ".join(line.text for line in unit))
    lines: list[str] = []
    current = lead + words[0]
    for word in words[1:]:
        extended = f"{current} {word}"
        if internal_display_width(extended) <= DOC_FILL_COLUMNS:
            current = extended
        else:
            lines.append(current)
            current = cont + word
    lines.append(current)
    return lines


DOC_FILL_COLUMNS = 79
