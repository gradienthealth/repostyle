"""Javadoc block-tag style: lowercase phrases, punctuated alike.

An `@param`, `@return`, `@throws`, or `@deprecated` description is a phrase
that opens in lowercase and takes no period (`@param timeout how long to wait
for a verdict`), the convention the JDK and Google's own Java code follow. A
description running to more than one sentence ends each with a period, and
then every tag in the same comment does too, so the tags read alike.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

from repostyle._shared import (
    _has_sentence_boundary,
    _join_source_lines,
    _terminal_punctuation_fault,
)
from repostyle.languages import JAVA, language_for
from repostyle.rules._javadoc import internal_javadoc_comments, internal_tag_caption_end
from repostyle.rules._prose_units import InternalProseUnit
from repostyle.rules._violation import (
    RS_LOWERCASE_ENTRY_DESCRIPTION,
    RS_TERMINAL_PUNCTUATION,
    Violation,
)


def check_javadoc_tag_punctuation(path: Path, source: str) -> Iterator[Violation]:
    """A Javadoc block-tag description is punctuated as its comment's tags are.

    A description is a phrase without a period. Once any `@param`, `@return`,
    `@throws`, or `@deprecated` description in a comment runs to more than one
    sentence, every one of them ends with a period instead. The fix drops or
    adds the period. A description whose last line holds only markup, such as a
    list's closing `</ul>`, is left alone, since no period belongs after a tag.
    """
    for fault in _punctuation_faults(source):
        yield Violation(
            fault.lineno,
            fault.column + 1,
            RS_TERMINAL_PUNCTUATION,
            _MESSAGES[fault.kind],
        )


_MESSAGES = {
    "extra": "a block-tag description is a phrase; drop the trailing period",
    "missing": (
        "a block tag in this comment runs to several sentences, so every tag "
        "description ends with a period"
    ),
}


def fix_javadoc_tag_punctuation(
    path: Path, source: str, skip_lines: frozenset[int] = frozenset()
) -> str:
    """Drops or adds each flagged block-tag period, RS030's fix for Java.

    Returns:
        The source with each flagged description repunctuated, unchanged when
        nothing changes or the file is not Java.
    """
    if language_for(path) is not JAVA:
        return source
    source_lines = source.splitlines()
    changed = False
    for fault in _punctuation_faults(source):
        if fault.lineno in skip_lines:
            continue
        line = source_lines[fault.lineno - 1]
        if fault.kind == "extra":
            line = line[: fault.column] + line[fault.column + 1 :]
        else:
            line = line[: fault.column] + "." + line[fault.column :]
        source_lines[fault.lineno - 1] = line
        changed = True
    return _join_source_lines(source, source_lines) if changed else source


def check_javadoc_tag_casing(path: Path, source: str) -> Iterator[Violation]:
    """A Javadoc block-tag description opens in lowercase.

    The description is a phrase completing its tag (`@return the count`), so it
    opens in lowercase. To stay mechanical the check fires only on a
    capitalized article, determiner, conjunction, or similar sentence opener
    (`The`, `A`, `If`, `Whether`, `True`), leaving a proper noun, an acronym,
    and a code name alone.
    """
    source_lines = source.splitlines()
    for unit, description in _tag_descriptions(source):
        first = description.split(maxsplit=1)[0]
        if first not in _SENTENCE_OPENERS:
            continue
        lineno = unit.linenos[0]
        yield Violation(
            lineno,
            source_lines[lineno - 1].find("@") + 1,
            RS_LOWERCASE_ENTRY_DESCRIPTION,
            f"a block-tag description is a lowercase phrase; write "
            f"'{first.lower()}', not '{first}'",
        )


_SENTENCE_OPENERS = frozenset(
    {
        "A",
        "All",
        "Always",
        "An",
        "Any",
        "Both",
        "Each",
        "Either",
        "Every",
        "False",
        "For",
        "From",
        "How",
        "If",
        "May",
        "Must",
        "Never",
        "No",
        "Not",
        "Optional",
        "Should",
        "Some",
        "That",
        "The",
        "These",
        "This",
        "Those",
        "To",
        "True",
        "What",
        "When",
        "Whether",
        "Which",
        "While",
        "Will",
        "With",
    }
)


class _Fault(NamedTuple):
    kind: str
    """`extra` for a period to drop, `missing` for one to add."""
    lineno: int
    """1-based line holding the description's last character."""
    column: int
    """0-based column of the period to drop, or where one goes."""


def _punctuation_faults(source: str) -> Iterator[_Fault]:
    """Yields each block-tag description punctuated against its comment."""
    source_lines = source.splitlines()
    for doc in internal_javadoc_comments(source):
        tags = list(_unit_descriptions(doc.units))
        is_prose = any(_has_sentence_boundary(text) for _, text in tags)
        for unit, description in tags:
            kind = _terminal_punctuation_fault(description, is_prose=is_prose)
            if kind is None or not doc.prose_lines[unit.lineno].strip():
                continue
            end = doc.text_ends[unit.lineno]
            line = source_lines[unit.lineno - 1]
            if kind == "missing":
                yield _Fault(kind, unit.lineno, end)
            elif line[end - 1 : end] == ".":
                yield _Fault(kind, unit.lineno, end - 1)


def _tag_descriptions(source: str) -> Iterator[tuple[InternalProseUnit, str]]:
    """Yields each prose-bearing block tag in `source` with its description."""
    for doc in internal_javadoc_comments(source):
        yield from _unit_descriptions(doc.units)


def _unit_descriptions(
    units: tuple[InternalProseUnit, ...],
) -> Iterator[tuple[InternalProseUnit, str]]:
    """Yields each prose-bearing tag unit with its description."""
    for unit in units:
        if unit.kind != "tag" or unit.text.split(maxsplit=1)[0] not in _PROSE_TAGS:
            continue
        description = unit.text[internal_tag_caption_end(unit.text) :].strip()
        if description:
            yield unit, description


_PROSE_TAGS = frozenset({"@param", "@return", "@throws", "@exception", "@deprecated"})
