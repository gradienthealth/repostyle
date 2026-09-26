"""Checks prose wrapping and docstring summary width."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from repostyle._comments import COMMENT_SUFFIXES
from repostyle._shared import (
    _parse_python,
    _walk_tree,
)
from repostyle.rules._comment_paragraphs import (
    internal_fillable_units,
)
from repostyle.rules._display_width import (
    internal_display_width,
    internal_holds_triple_quote,
    internal_span_crosses_line,
)
from repostyle.rules._fill_units import (
    internal_is_bare_string_literal_statement,
)
from repostyle.rules._reflow import (
    DOC_FILL_COLUMNS,
    internal_unit_violations,
)
from repostyle.rules._violation import (
    RS_DOC_SUMMARY_OVERFLOW,
    Violation,
)


def check_doc_fill(path: Path, source: str) -> Iterator[Violation]:
    """Docstring and comment paragraphs must fill to 79 columns.

    A paragraph line may not end while the next line's first word still fits
    within the limit, and may not run past the limit while a break is
    available. A backtick `...` span is one unbreakable token, so a space
    inside it is not an available break, as with a URL. Summary lines,
    single-line docstrings, section headers, label lines, code fences, doctest
    lines, comment directives, preformatted lines, and lines carrying URLs are
    exempt, as is a unit with a backtick span hard-wrapped across lines;
    bullets and section entries wrap as hanging paragraphs. Docstrings are read
    from Python only; comments are read from Python, TOML, YAML, and shell
    alike. YAML prose is read too, from folded (`>`) block scalars, whose line
    breaks fold to spaces so that a rewrap leaves the value unchanged; a
    literal (`|`) scalar keeps its breaks as content and is left alone. A
    folded scalar counts as prose only where it closes on terminal punctuation,
    which leaves ragged prose that omits its closing period unenforced: RS030
    does not reach a scalar either, reading `#` comments alone, and it cannot,
    since the punctuation it looks for is the very signal that separates prose
    from the `>` blocks holding an expression.
    """
    if path.suffix not in COMMENT_SUFFIXES:
        return
    if path.suffix == ".py" and _parse_python(path, source) is None:
        return
    for unit in internal_fillable_units(path, source):
        if internal_holds_triple_quote(unit) or internal_span_crosses_line(unit):
            continue
        yield from internal_unit_violations(unit)


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
    for node in _walk_tree(tree):
        if not internal_is_bare_string_literal_statement(node):
            continue
        lineno = node.value.lineno
        rendered = source_lines[lineno - 1].rstrip()
        if internal_display_width(rendered) <= DOC_FILL_COLUMNS:
            continue
        indent = len(rendered) - len(rendered.lstrip())
        yield Violation(
            lineno,
            indent + 1,
            RS_DOC_SUMMARY_OVERFLOW,
            f"docstring summary line exceeds {DOC_FILL_COLUMNS} columns; shorten it by hand, since a one-line summary cannot be rewrapped",
        )
