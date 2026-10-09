"""The documentation blocks of a source file, read the same in every language.

A doc block is one unit's documentation: a Python docstring or a Java Javadoc
comment. A prose rule that grades only what the documentation says -- its mood,
its punctuation, its spelling of a product name -- reads these blocks instead
of walking a language's syntax, so it reaches every language that contributes
them. A rule that needs the documented code itself, such as the parameters an
`Args:` section must name, still reads that language's syntax.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

from repostyle._shared import _parse_python
from repostyle.languages import JAVA, PYTHON, language_for
from repostyle.rules._docstring_edits import internal_blank_outside_docstring
from repostyle.rules._docstring_source import (
    internal_docstring_constant,
    internal_docstring_prose_units,
    internal_docstring_summary_line,
)
from repostyle.rules._javadoc import (
    InternalJavadoc,
    internal_javadoc_comments,
    internal_tag_caption_end,
)
from repostyle.rules._prose_analysis import InternalENTRY_CAPTION_PATTERN
from repostyle.rules._prose_sources import internal_walk_docstring_owners
from repostyle.rules._prose_units import InternalProseUnit


class InternalDocBlock(NamedTuple):
    lineno: int
    """1-based line a finding about the whole block points at."""
    col: int
    """1-based column a finding about the whole block points at."""
    summary: str
    """The block's opening line of prose, markup resolved to plain text."""
    units: tuple[InternalProseUnit, ...]
    """The block's summary, body, entry, bullet, and `tag` units in order."""
    scan_lines: tuple[tuple[int, str], ...]
    """Each prose line, full width, with code and captions blanked."""
    is_javadoc: bool
    """Whether the block is Javadoc rather than a Python docstring."""


@lru_cache(maxsize=128)
def internal_doc_blocks(path: Path, source: str) -> tuple[InternalDocBlock, ...]:
    """Returns every documentation block in `source`, by its file's language.

    A Python file contributes the docstring of each module, class, and
    function, anchored on its owner; a Java file contributes each Javadoc
    comment, anchored on its opening `/**`. Every other file, and a Python file
    that does not parse, contributes none.
    """
    language = language_for(path)
    if language is PYTHON:
        return tuple(_python_blocks(path, source))
    if language is JAVA:
        return tuple(_javadoc_block(doc) for doc in internal_javadoc_comments(source))
    return ()


def _python_blocks(path: Path, source: str) -> Iterator[InternalDocBlock]:
    """Yields the docstring block of each owner in a Python `source`."""
    tree = _parse_python(path, source)
    if tree is None:
        return
    source_lines = source.splitlines()
    for node in internal_walk_docstring_owners(tree):
        constant = internal_docstring_constant(node)
        docstring = ast.get_docstring(node, clean=True)
        if constant is None or docstring is None:
            continue
        units = tuple(internal_docstring_prose_units(constant))
        yield InternalDocBlock(
            getattr(node, "lineno", 1),
            getattr(node, "col_offset", 0) + 1,
            internal_docstring_summary_line(docstring),
            units,
            tuple(_python_scan_lines(units, constant, source_lines)),
            is_javadoc=False,
        )


def _python_scan_lines(
    units: tuple[InternalProseUnit, ...],
    constant: ast.Constant,
    source_lines: list[str],
) -> Iterator[tuple[int, str]]:
    """Yields each docstring prose line confined to the literal's columns.

    A one-line `def` or `class` signature and a trailing comment sharing a line
    are blanked, and so is an entry unit's leading `name:` caption, since a
    parameter name is code the author spells rather than prose.
    """
    prose_lines = sorted({lineno for unit in units for lineno in unit.linenos})
    caption_lines = {unit.linenos[0] for unit in units if unit.kind == "entry"}
    for lineno in prose_lines:
        line = internal_blank_outside_docstring(
            source_lines[lineno - 1], lineno, constant
        )
        yield lineno, _blank_entry_caption(line) if lineno in caption_lines else line


def _blank_entry_caption(line: str) -> str:
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


def _javadoc_block(doc: InternalJavadoc) -> InternalDocBlock:
    """Builds the doc block of one segmented Javadoc comment."""
    summary = next((unit.text for unit in doc.units if unit.kind == "summary"), "")
    return InternalDocBlock(
        doc.lineno,
        doc.col,
        summary,
        doc.units,
        tuple(_javadoc_scan_lines(doc)),
        is_javadoc=True,
    )


def _javadoc_scan_lines(doc: InternalJavadoc) -> Iterator[tuple[int, str]]:
    """Yields each Javadoc prose line with its block-tag caption blanked."""
    caption_lines = {unit.linenos[0] for unit in doc.units if unit.kind == "tag"}
    prose_lines = sorted({lineno for unit in doc.units for lineno in unit.linenos})
    for lineno in prose_lines:
        line = doc.prose_lines[lineno]
        if lineno in caption_lines:
            start = len(line) - len(line.lstrip())
            end = start + internal_tag_caption_end(line[start:])
            line = line[:start] + " " * (end - start) + line[end:]
        yield lineno, line
