"""Sentence casing, punctuation, and temporal-language rules."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from itertools import pairwise
from pathlib import Path

from repostyle._shared import (
    _blank_prose_spans,
    _parse_python,
    _standalone_comment_blocks,
    _temporal_markers,
    _terminal_punctuation_fault,
)
from repostyle.languages import COMMENT_SUFFIXES
from repostyle.rules._doc_blocks import internal_doc_blocks
from repostyle.rules._docstring_edits import (
    internal_blank_outside_docstring,
    internal_comment_bullet_lists,
)
from repostyle.rules._docstring_source import (
    InternalLITERAL_CONSTANTS,
    internal_docstring_constant,
    internal_docstring_prose_units,
)
from repostyle.rules._prose_analysis import (
    internal_docstring_bullet_lists,
    internal_entry_description,
    internal_miscased_bullet_items,
    internal_module_bound_names,
    internal_name_location,
    internal_opens_with_lowercase_prose,
    internal_unbackticked_references,
)
from repostyle.rules._prose_sources import (
    internal_terminal_punctuation_message,
    internal_walk_docstring_owners,
)
from repostyle.rules._prose_units import InternalProseUnit
from repostyle.rules._violation import (
    RS_INLINE_NUMBERED_LIST,
    RS_LOWERCASE_ENTRY_DESCRIPTION,
    RS_TEMPORAL_MARKER,
    RS_TERMINAL_PUNCTUATION,
    RS_UNBACKTICKED_CODE_REFERENCE,
    Violation,
)

_ORDERED_MARKER_PATTERN = re.compile(r"(?<!\S)(\d+)[.)](?=\s)")

_NumberedMarker = tuple[int, int, int, bool]


def check_docstring_terminal_punctuation(
    path: Path, source: str
) -> Iterator[Violation]:
    """Every docstring and Javadoc prose unit ends with terminal punctuation.

    A summary closes with `.`, `!`, or `?`, as PEP 257 prescribes for a
    docstring and Google Java style for Javadoc, and the house extends the rule
    to every body paragraph and to a docstring's `Args:`, `Returns:`,
    `Raises:`, and `Yields:` entries. Code (doctests, `Example:` sections,
    fenced and `<pre>` blocks), bullet items, a list-introducing colon, a unit
    ending in a URL, and a Javadoc block tag, which follows its own convention,
    are exempt.
    """
    for block in internal_doc_blocks(path, source):
        for unit in block.units:
            if unit.kind in _UNPUNCTUATED_KINDS:
                continue
            if _terminal_punctuation_fault(unit.text, is_prose=True) is None:
                continue
            yield Violation(
                unit.lineno,
                unit.col,
                RS_TERMINAL_PUNCTUATION,
                internal_terminal_punctuation_message(unit.kind),
            )


_UNPUNCTUATED_KINDS = frozenset({"bullet", "tag"})


def check_lowercase_entry_description(path: Path, source: str) -> Iterator[Violation]:
    """A Google-section entry's description opens with a capital letter.

    An `Args:`, `Returns:`, `Raises:`, or `Yields:` entry states its
    description as a full sentence, so it opens with a capital just as RS030
    requires it to close with a period -- the two rules are the opening-capital
    and closing-period halves of the same full-sentence convention. `bar: A
    bar.`, not `bar: a bar.`; `NotFoundError: If a foo is not found.`, not
    `NotFoundError: if a foo is not found.`.

    Only a lowercase ASCII prose letter opening the description fires. A
    description opening with a backtick code span, an inherently-lowercase code
    token (a parameter name or a dotted path like `json.dumps`), a digit, or
    any other non-letter is left alone, so a legitimately lowercase opener does
    not draw a false finding. An empty description is skipped.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    source_lines = source.splitlines()
    for node in internal_walk_docstring_owners(tree):
        constant = internal_docstring_constant(node)
        if constant is None:
            continue
        for unit in internal_docstring_prose_units(constant):
            if unit.kind != "entry":
                continue
            if not internal_opens_with_lowercase_prose(
                internal_entry_description(unit.text)
            ):
                continue
            lineno = unit.linenos[0]
            line = source_lines[lineno - 1]
            yield Violation(
                lineno,
                len(line) - len(line.lstrip()) + 1,
                RS_LOWERCASE_ENTRY_DESCRIPTION,
                "a section entry description opens in lowercase; begin it with a capital letter",
            )


def check_bullet_item_casing(path: Path, source: str) -> Iterator[Violation]:
    """A bulleted list holding a multi-sentence item is sentence-cased.

    A list item running more than one sentence is prose, and prose opens with
    a capital; once any item in a list is such prose, every item in the list
    opens with a capital, so the list reads in one register -- `- The thing.
    Does a foo.` beside `- The other thing.`, never beside `- the other
    thing`. A list whose items are all single-sentence fragments may stay
    lowercase, since a fragment continues the sentence that introduced the
    list. As in RS047, an item opening with a backtick span, an
    inherently-lowercase code token (a dotted path or a distinctive-shaped
    identifier), a digit, or any other non-letter never fires.

    A list is a run of consecutive bullet items at one indent, unbroken by a
    body paragraph; a nested deeper-indented list is judged on its own. A
    sentence boundary inside a backtick span or a URL does not count toward an
    item being multi-sentence.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    source_lines = source.splitlines()
    for node in internal_walk_docstring_owners(tree):
        constant = internal_docstring_constant(node)
        if constant is None:
            continue
        units = internal_docstring_prose_units(constant)
        for items in internal_docstring_bullet_lists(units, source_lines):
            yield from internal_miscased_bullet_items(items)


def check_bullet_item_casing_in_comments(
    path: Path, source: str
) -> Iterator[Violation]:
    """A comment's bulleted list follows RS053's sentence-casing contract.

    Applies `check_bullet_item_casing` to the bulleted lists inside standalone
    comment blocks, read from Python, TOML, YAML, and shell comments alike. A
    line indented past the item's marker within the same block wraps the item;
    a same-indent bullet continues the list; any other line ends it.
    """
    if path.suffix not in COMMENT_SUFFIXES:
        return
    for block in _standalone_comment_blocks(path, source):
        for items in internal_comment_bullet_lists(block):
            yield from internal_miscased_bullet_items(items)


def check_inline_numbered_list(path: Path, source: str) -> Iterator[Violation]:
    """A numbered sequence in docstring prose puts each item on its own line.

    Two consecutive ordered markers in one prose unit express list structure,
    so keeping either marker inline makes the sequence harder to scan and
    prevents Markdown from rendering it as a list. A marker inside a code span,
    fenced block, doctest, or `Example:` section is not prose and is ignored.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    source_lines = source.splitlines()
    for node in internal_walk_docstring_owners(tree):
        constant = internal_docstring_constant(node)
        if constant is None:
            continue
        markers = list(_numbered_markers(constant, source_lines))
        culprit = _first_inline_marker(markers, source_lines)
        if culprit is not None:
            yield Violation(
                culprit[1],
                culprit[2],
                RS_INLINE_NUMBERED_LIST,
                "numbered items run inline; put each item on its own line and align continuations beneath its text",
            )


def _first_inline_marker(
    markers: list[_NumberedMarker], source_lines: list[str]
) -> _NumberedMarker | None:
    """Returns the first inline marker in a consecutive numbered pair."""
    for first, second in pairwise(markers):
        if (
            second[0] == first[0] + 1
            and (first[3] or second[3])
            and not _has_blank_between(first, second, source_lines)
        ):
            return first if first[3] else second
    return None


def _has_blank_between(
    first: _NumberedMarker,
    second: _NumberedMarker,
    source_lines: list[str],
) -> bool:
    """Reports whether a blank source line separates two markers."""
    between = source_lines[first[1] : second[1] - 1]
    return any(not line.strip() for line in between)


def _numbered_markers(
    constant: ast.Constant, source_lines: list[str]
) -> Iterator[_NumberedMarker]:
    """Yields each ordered marker and whether it sits inline."""
    for unit in internal_docstring_prose_units(constant):
        yield from _unit_numbered_markers(unit, constant, source_lines)


def _unit_numbered_markers(
    unit: InternalProseUnit, constant: ast.Constant, source_lines: list[str]
) -> Iterator[_NumberedMarker]:
    """Yields the ordered markers in one prose unit."""
    for lineno in dict.fromkeys(unit.linenos):
        line = internal_blank_outside_docstring(
            source_lines[lineno - 1], lineno, constant
        )
        matches = _ORDERED_MARKER_PATTERN.finditer(_blank_prose_spans(line))
        for index, match in enumerate(matches):
            is_item_marker = (
                unit.kind == "bullet" and lineno == unit.linenos[0] and index == 0
            )
            yield (
                int(match.group(1)),
                lineno,
                match.start() + 1,
                not is_item_marker,
            )


def check_docstring_temporal_markers(path: Path, source: str) -> Iterator[Violation]:
    """Flags a temporal or edit-narrative marker in docstring prose.

    A curated set of phrases -- naming what the code once did, or how a change
    was reached -- narrates the edit rather than the unit's present contract,
    so it belongs in the commit message, not durable docstring prose. This is
    the common source of an agent leaking the session's design discussion and
    the diff's story into the code. A marker quoted inside a backtick span or a
    Javadoc code tag is a referenced token, not narration, and is left alone.
    Each prose unit -- summary, body paragraph, section entry, or Javadoc block
    tag -- is scanned; a code span, doctest, `Example:` block, or `<pre>` block
    is not. This is the mechanical floor under review, which judges the
    ambiguous cases this tight set deliberately leaves out.
    """
    for block in internal_doc_blocks(path, source):
        for unit in block.units:
            for marker in _temporal_markers(unit.text):
                yield Violation(
                    unit.lineno,
                    unit.col,
                    RS_TEMPORAL_MARKER,
                    f"docstring narrates the edit history with '{marker}'; state the code's current contract, not how it changed",
                )


def check_unbackticked_code_reference(path: Path, source: str) -> Iterator[Violation]:
    """Flags a code name in docstring prose left without backticks.

    A word in docstring prose that matches a name the module itself binds -- a
    parameter, an import, a function or class, an accessed attribute -- or one
    of the literals `None`, `True`, and `False` reads as a code reference, and
    the house style sets a code token in single backticks. To stay mechanical
    the check fires only where a word cannot be ordinary English: an
    underscore, a digit, or an interior capital beside a lowercase letter
    (`skip_lines`, `col_offset`, `HttpClient`) marks it as code wherever it
    sits. A literal fires mid-sentence, where a capital `None` is unambiguous,
    but not at a sentence start, where it could open an English clause. A
    plain-lowercase word (a `path` parameter), a Titlecase or all-caps word
    that also reads as English (`Path`, `Note`, `WARNING`), a backticked span,
    a URI, and a doctest are all left alone.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    known = internal_module_bound_names(tree) | InternalLITERAL_CONSTANTS
    source_lines = source.splitlines()
    for node in internal_walk_docstring_owners(tree):
        constant = internal_docstring_constant(node)
        if constant is None:
            continue
        names: list[str] = []
        for unit in internal_docstring_prose_units(constant):
            for name in internal_unbackticked_references(unit, known):
                if name not in names:
                    names.append(name)
        for name in names:
            lineno, col = internal_name_location(source_lines, constant, name)
            yield Violation(
                lineno,
                col,
                RS_UNBACKTICKED_CODE_REFERENCE,
                f"`{name}` in a docstring reads as a code reference but is not backticked; wrap it in single backticks",
            )
