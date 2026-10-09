"""Typography and terminology rules for prose."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path

from repostyle._shared import (
    STANDARD_SENTENCE_DASH,
    _blank_prose_spans,
    _join_source_lines,
    _nonstandard_dashes_in_prose,
)
from repostyle.rules._doc_blocks import InternalDocBlock, internal_doc_blocks
from repostyle.rules._violation import (
    RS_DISFAVORED_GCP_TERM,
    RS_NONSTANDARD_DASH,
    Violation,
)
from repostyle.rules.naming import (
    disfavored_gcp_terms_in_prose,
)


def check_disfavored_gcp_term_in_docstrings(
    path: Path, source: str
) -> Iterator[Violation]:
    """Flags a disfavored Google Cloud product or brand name in documentation.

    Docstrings and Javadoc are read alike. A whole-word occurrence of a term in
    RS050's curated map (`GCP`, `GCS`, `Google Cloud Platform`, `Big Query`,
    `PubSub`, ...) is flagged and, under `--fix`, rewritten to its current form
    (`Google Cloud`, `Cloud Storage`, `Pub/Sub`, ...). The match is whole-word
    and case-insensitive, so a substring (`GCS` in `GCSError`) and a term glued
    to a hyphen are left alone. So is a term in code: a backtick span
    (`gcp.storage`), a Javadoc `{@code}` or `{@link}` tag, a URL, or the
    parameter caption leading an `Args:` entry or a block tag. Only unambiguous
    substitutions are mapped; a bare `Storage` or `Monitoring`, an ordinary
    English word, is left to review.
    """
    for lineno, offset, found, preferred in _doc_faults(
        internal_doc_blocks(path, source), disfavored_gcp_terms_in_prose
    ):
        yield Violation(
            lineno,
            offset + 1,
            RS_DISFAVORED_GCP_TERM,
            f"docstring uses the disfavored name '{found}'; write '{preferred}'",
        )


def fix_disfavored_gcp_term_in_docstrings(
    path: Path, source: str, skip_lines: frozenset[int] = frozenset()
) -> str:
    """Rewrites each disfavored Google Cloud name in a docstring, RS050's fix.

    Each occurrence the docstring check flags is replaced in place with its
    preferred form. A replacement changes length, so a line's faults are
    applied right to left, keeping each earlier offset valid. A unit whose line
    is in `skip_lines` is left alone.

    Returns:
        The source with each flagged name rewritten, unchanged when nothing
        rewrites.
    """
    faults = _doc_faults(
        internal_doc_blocks(path, source), disfavored_gcp_terms_in_prose
    )
    return _rewrite_faults(source, faults, skip_lines)


def check_nonstandard_dash_in_docstrings(
    path: Path, source: str
) -> Iterator[Violation]:
    """Flags a nonstandard sentence dash in a docstring or Javadoc.

    Prose sets a clause off with the house sentence dash: the spaced double
    hyphen ` -- ` in a Python docstring, and the spaced em dash ` — ` in
    Javadoc, which renders as HTML, where ` -- ` would show as two hyphens. Any
    other dash doing sentence work is flagged and, under `--fix`, rewritten to
    the standard form: an em dash glued or half-spaced, a spaced en dash, a
    letter-flanked spaced hyphen, and a double hyphen where it is not the
    standard. An occurrence inside a backtick span (`git log -- path`), a
    Javadoc code tag, or a URL is left alone, as are an unspaced en dash (an
    `RSnnn` or numeric range) and a hyphen not flanked by letters (arithmetic,
    a negative number, a CLI flag, a bullet marker), so only a dash doing
    sentence work fires.
    """
    for block in internal_doc_blocks(path, source):
        standard = _JAVADOC_DASH if block.is_javadoc else STANDARD_SENTENCE_DASH
        for lineno, offset, found, _ in _doc_faults((block,), _dash_scanner(block)):
            yield Violation(
                lineno,
                offset + 1,
                RS_NONSTANDARD_DASH,
                f"docstring uses a nonstandard sentence dash {found!r}; write {standard!r}",
            )


def fix_nonstandard_dash_in_docstrings(
    path: Path, source: str, skip_lines: frozenset[int] = frozenset()
) -> str:
    """Rewrites each nonstandard sentence dash in a docstring, RS054's fix.

    Each occurrence the check flags is replaced in place with its block's
    standard dash. A replacement changes length, so a line's faults are applied
    right to left, keeping each earlier offset valid. A unit whose line is in
    `skip_lines` is left alone.

    Returns:
        The source with each flagged dash rewritten, unchanged when nothing
        rewrites.
    """
    faults = [
        fault
        for block in internal_doc_blocks(path, source)
        for fault in _doc_faults((block,), _dash_scanner(block))
    ]
    return _rewrite_faults(source, faults, skip_lines)


def _dash_scanner(block: InternalDocBlock) -> _LineScanner:
    """Returns the dash scanner for a block's language."""
    return _javadoc_dashes if block.is_javadoc else _nonstandard_dashes_in_prose


def _javadoc_dashes(line: str) -> Iterator[tuple[int, str, str]]:
    """Yields `(offset, found, replacement)` per nonstandard Javadoc dash.

    The standard is a spaced em dash. At a wrap point the dash keeps only the
    space on its prose side, so a dash ending or opening a line is standard as
    ` —` or `— `, and a rewrite never leaves a space at a line edge.
    """
    masked = _blank_prose_spans(line)
    found: set[tuple[int, str]] = set()
    for pattern in _JAVADOC_DASH_PATTERNS:
        for match in pattern.finditer(masked):
            found.add((match.start(), match.group()))
    for offset, text in sorted(found):
        is_line_start = not line[:offset].strip()
        is_line_end = not line[offset + len(text) :].strip()
        if is_line_start:
            offset, text = offset + len(text) - len(text.lstrip()), text.lstrip()
        if is_line_end:
            text = text.rstrip()
        replacement = (
            ("" if is_line_start else " ") + "—" + ("" if is_line_end else " ")
        )
        if text != replacement:
            yield offset, text, replacement


_JAVADOC_DASH = " — "

_JAVADOC_DASH_PATTERNS = (
    re.compile(r" ?— ?"),
    re.compile(r" – "),  # noqa: RUF001
    re.compile(r"(?<=[A-Za-z]) - (?=[A-Za-z])"),
    re.compile(r" --(?: |$)"),
    re.compile(r"(?<=[A-Za-z])--(?=[A-Za-z])"),
)


_LineScanner = Callable[[str], Iterable[tuple[int, str, str]]]

_LineFault = tuple[int, str, str]


def _doc_faults(
    blocks: Iterable[InternalDocBlock], scanner: _LineScanner
) -> Iterator[tuple[int, int, str, str]]:
    """Yields `(lineno, offset, found, replacement)` per fault `scanner` finds.

    Scans each prose line of each block, already confined to the block's own
    columns with code and captions blanked, so a one-line signature, a trailing
    comment, a parameter caption, and a code span are never read as prose.
    """
    for block in blocks:
        for lineno, line in block.scan_lines:
            for offset, found, replacement in scanner(line):
                yield (lineno, offset, found, replacement)


def _rewrite_faults(
    source: str,
    faults: Iterable[tuple[int, int, str, str]],
    skip_lines: frozenset[int],
) -> str:
    """Returns `source` with each fault off a `skip_lines` line rewritten."""
    source_lines = source.splitlines()
    faults_by_line: dict[int, list[_LineFault]] = {}
    for lineno, offset, found, replacement in faults:
        if lineno not in skip_lines:
            faults_by_line.setdefault(lineno, []).append((offset, found, replacement))
    for lineno, line_faults in faults_by_line.items():
        source_lines[lineno - 1] = _apply_line_faults(
            source_lines[lineno - 1], line_faults
        )
    return _join_source_lines(source, source_lines) if faults_by_line else source


def _apply_line_faults(line: str, faults: list[_LineFault]) -> str:
    """Returns `line` with each `(offset, found, replacement)` fault applied.

    Faults are applied in descending offset order, so a preceding replacement's
    length change never shifts a later offset.
    """
    for offset, found, replacement in sorted(faults, reverse=True):
        if line[offset : offset + len(found)] == found:
            line = line[:offset] + replacement + line[offset + len(found) :]
    return line
