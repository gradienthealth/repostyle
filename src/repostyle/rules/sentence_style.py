"""Sentence casing, punctuation, and temporal-language rules."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from repostyle._comments import COMMENT_SUFFIXES
from repostyle._shared import (
    _parse_python,
    _standalone_comment_blocks,
    _temporal_markers,
    _terminal_punctuation_fault,
)
from repostyle.rules._docstring_edits import (
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
from repostyle.rules._violation import (
    RS_LOWERCASE_ENTRY_DESCRIPTION,
    RS_TEMPORAL_MARKER,
    RS_TERMINAL_PUNCTUATION,
    RS_UNBACKTICKED_CODE_REFERENCE,
    Violation,
)


def check_docstring_terminal_punctuation(
    path: Path, source: str
) -> Iterator[Violation]:
    """Every docstring prose unit must end with terminal punctuation.

    A summary, a body paragraph, and an `Args:`, `Returns:`, `Raises:`, or
    `Yields:` entry each close with `.`, `!`, or `?`, as PEP 257 prescribes for
    the summary and the house style extends to the rest. Code (doctests,
    `Example:` sections, fenced blocks), bullet items, a list-introducing
    colon, and a unit ending in a URL are exempt.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in internal_walk_docstring_owners(tree):
        constant = internal_docstring_constant(node)
        if constant is None:
            continue
        for unit in internal_docstring_prose_units(constant):
            if unit.kind == "bullet":
                continue
            if _terminal_punctuation_fault(unit.text, is_prose=True) is None:
                continue
            yield Violation(
                unit.lineno,
                unit.col,
                RS_TERMINAL_PUNCTUATION,
                internal_terminal_punctuation_message(unit.kind),
            )


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


def check_docstring_temporal_markers(path: Path, source: str) -> Iterator[Violation]:
    """Flags a temporal or edit-narrative marker in docstring prose.

    A curated set of phrases -- naming what the code once did, or how a change
    was reached -- narrates the edit rather than the unit's present contract,
    so it belongs in the commit message, not durable docstring prose. This is
    the common source of an agent leaking the session's design discussion and
    the diff's story into the code. A marker quoted inside a backtick span is a
    referenced token, not narration, and is left alone. Each prose unit --
    summary, body paragraph, or section entry -- is scanned; a code span,
    doctest, or `Example:` block is not. This is the mechanical floor under
    review, which judges the ambiguous cases this tight set deliberately leaves
    out.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in internal_walk_docstring_owners(tree):
        constant = internal_docstring_constant(node)
        if constant is None:
            continue
        for unit in internal_docstring_prose_units(constant):
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
