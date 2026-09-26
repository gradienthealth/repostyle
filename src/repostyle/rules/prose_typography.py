"""Typography and terminology rules for prose."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

from repostyle._shared import (
    STANDARD_SENTENCE_DASH,
    _join_source_lines,
    _nonstandard_dashes_in_prose,
    _parse_python,
)
from repostyle.rules._docstring_edits import (
    internal_blank_outside_docstring,
)
from repostyle.rules._docstring_source import (
    internal_docstring_constant,
    internal_docstring_prose_units,
)
from repostyle.rules._prose_analysis import (
    InternalENTRY_CAPTION_PATTERN,
)
from repostyle.rules._prose_sources import (
    internal_walk_docstring_owners,
)
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
    """Flags a disfavored Google Cloud product or brand name in a docstring.

    A whole-word occurrence of a term in RS050's curated map (`GCP`, `GCS`,
    `Google Cloud Platform`, `Big Query`, `PubSub`, ...) is flagged and, under
    `--fix`, rewritten to its current form (`Google Cloud`, `Cloud Storage`,
    `Pub/Sub`, ...). The match is whole-word and case-insensitive, so a
    substring (`GCS` in `GCSError`) and a term glued to a hyphen are left
    alone, as is an occurrence inside a backtick span (the identifier
    `gcp.storage`) or a URL, and an `Args:` entry's leading parameter caption.
    Only unambiguous substitutions are mapped; a bare `Storage` or
    `Monitoring`, an ordinary English word, is left to review.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    source_lines = source.splitlines()
    for node in internal_walk_docstring_owners(tree):
        constant = internal_docstring_constant(node)
        if constant is None:
            continue
        for lineno, offset, found, preferred in _docstring_gcp_term_faults(
            constant, source_lines
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
    tree = _parse_python(path, source)
    if tree is None:
        return source
    source_lines = source.splitlines()
    faults_by_line: dict[int, list[_LineFault]] = {}
    for node in internal_walk_docstring_owners(tree):
        constant = internal_docstring_constant(node)
        if constant is None:
            continue
        for lineno, offset, found, preferred in _docstring_gcp_term_faults(
            constant, source_lines
        ):
            if lineno not in skip_lines:
                faults_by_line.setdefault(lineno, []).append((offset, found, preferred))
    for lineno, faults in faults_by_line.items():
        source_lines[lineno - 1] = _apply_line_faults(source_lines[lineno - 1], faults)
    return _join_source_lines(source, source_lines) if faults_by_line else source


def check_nonstandard_dash_in_docstrings(
    path: Path, source: str
) -> Iterator[Violation]:
    """Flags a nonstandard sentence dash in a docstring.

    Prose sets a clause off with the house sentence dash, the spaced double
    hyphen ` -- `. An em dash (spaced or glued), a spaced en dash, a
    letter-flanked spaced hyphen, and a mis-spaced double hyphen are flagged
    and, under `--fix`, rewritten to the standard form. An occurrence inside a
    backtick span (`git log -- path`) or a URL is left alone, as are an
    unspaced en dash (an `RSnnn` or numeric range) and a hyphen not flanked by
    letters (arithmetic, a negative number, a CLI flag, a bullet marker), so
    only a dash doing sentence work fires.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    source_lines = source.splitlines()
    for node in internal_walk_docstring_owners(tree):
        constant = internal_docstring_constant(node)
        if constant is None:
            continue
        for lineno, offset, found, _ in _docstring_dash_faults(constant, source_lines):
            yield Violation(
                lineno,
                offset + 1,
                RS_NONSTANDARD_DASH,
                f"docstring uses a nonstandard sentence dash {found!r}; write {STANDARD_SENTENCE_DASH!r}",
            )


def fix_nonstandard_dash_in_docstrings(
    path: Path, source: str, skip_lines: frozenset[int] = frozenset()
) -> str:
    """Rewrites each nonstandard sentence dash in a docstring, RS054's fix.

    Each occurrence the docstring check flags is replaced in place with the
    house ` -- `. A replacement changes length, so a line's faults are applied
    right to left, keeping each earlier offset valid. A unit whose line is in
    `skip_lines` is left alone.

    Returns:
        The source with each flagged dash rewritten, unchanged when nothing
        rewrites.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return source
    source_lines = source.splitlines()
    faults_by_line: dict[int, list[_LineFault]] = {}
    for node in internal_walk_docstring_owners(tree):
        constant = internal_docstring_constant(node)
        if constant is None:
            continue
        for lineno, offset, found, replacement in _docstring_dash_faults(
            constant, source_lines
        ):
            if lineno not in skip_lines:
                faults_by_line.setdefault(lineno, []).append(
                    (offset, found, replacement)
                )
    for lineno, faults in faults_by_line.items():
        source_lines[lineno - 1] = _apply_line_faults(source_lines[lineno - 1], faults)
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


_LineFault = tuple[int, str, str]


def _docstring_dash_faults(
    constant: ast.Constant, source_lines: list[str]
) -> Iterator[tuple[int, int, str, str]]:
    """Yields `(lineno, offset, found, replacement)` per nonstandard dash.

    Scans each source line the docstring's prose units occupy -- the segmenter
    already drops fences, doctests, verbatim lines, and `Example:` sections --
    confined to the docstring literal's own columns, so a one-line signature or
    a trailing comment sharing the line is excluded. An entry's leading `name:`
    caption needs no blanking, since a caption is one unspaced token no dash
    form can straddle.
    """
    units = internal_docstring_prose_units(constant)
    prose_lines = frozenset(lineno for unit in units for lineno in unit.linenos)
    for lineno in sorted(prose_lines):
        line = internal_blank_outside_docstring(
            source_lines[lineno - 1], lineno, constant
        )
        for offset, found, replacement in _nonstandard_dashes_in_prose(line):
            yield (lineno, offset, found, replacement)


def _docstring_gcp_term_faults(
    constant: ast.Constant, source_lines: list[str]
) -> Iterator[tuple[int, int, str, str]]:
    """Yields `(lineno, offset, found, preferred)` for each disfavored name.

    Scans each source line the docstring's prose units occupy -- the segmenter
    already drops fences, doctests, and `Example:` sections -- confined to the
    docstring literal's own columns, so a one-line `def`/`class` signature or a
    trailing comment sharing the line is excluded, and with an entry unit's
    leading `name:` caption blanked, so a parameter named for a Google Cloud
    term is not mistaken for prose to correct.
    """
    units = internal_docstring_prose_units(constant)
    prose_lines = frozenset(lineno for unit in units for lineno in unit.linenos)
    caption_lines = {unit.linenos[0] for unit in units if unit.kind == "entry"}
    for lineno in sorted(prose_lines):
        line = internal_blank_outside_docstring(
            source_lines[lineno - 1], lineno, constant
        )
        scanned = (
            internal_blank_entry_caption(line) if lineno in caption_lines else line
        )
        for offset, found, preferred in disfavored_gcp_terms_in_prose(scanned):
            yield (lineno, offset, found, preferred)


def internal_blank_entry_caption(line: str) -> str:
    """Blanks an entry line's leading `name:` caption to equal-length spaces.

    The blanking preserves every following character's offset, so a token found
    past the caption still indexes the original `line`. A line carrying no
    caption is returned unchanged.
    """
    stripped = line.lstrip()
    match = InternalENTRY_CAPTION_PATTERN.match(stripped)
    if match is None:
        return line
    indent = len(line) - len(stripped)
    end = indent + match.end()
    return line[:indent] + " " * (end - indent) + line[end:]
