"""Internal docstring-rule implementation partition 1."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

from repostyle._shared import (
    _join_source_lines,
    _parse_python,
)
from repostyle.rules._docstrings_impl_7 import (
    internal_docstring_section_alias_faults,
)
from repostyle.rules._docstrings_impl_9 import (
    internal_doc_lines,
    internal_docstring_constant,
    internal_has_indented_section_body,
)
from repostyle.rules._docstrings_impl_10 import (
    InternalSECTION_HEADERS,
)
from repostyle.rules._docstrings_impl_11 import (
    internal_unfenced_margin_lines,
    internal_walk_docstring_owners,
)
from repostyle.rules._violation import (
    RS_DOCSTRING_SECTION_ALIAS,
    RS_DOCSTRING_SECTION_ORDER,
    RS_INVALID_DOCSTRING_SECTION,
    RS_NO_ATTRIBUTES_BLOCK,
    Violation,
)


def check_no_attributes_block(path: Path, source: str) -> Iterator[Violation]:
    """Docstrings must not use a Google `Attributes:` block."""
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in internal_walk_docstring_owners(tree):
        docstring = ast.get_docstring(node, clean=False)
        if docstring is None:
            continue
        if ATTRIBUTES_SECTION_PATTERN.search(docstring) is None:
            continue
        yield Violation(
            getattr(node, "lineno", 1),
            getattr(node, "col_offset", 0) + 1,
            RS_NO_ATTRIBUTES_BLOCK,
            "use per-field attribute docstrings, not a Google `Attributes:` block",
        )


ATTRIBUTES_SECTION_PATTERN = re.compile("^\\s*Attributes:\\s*$", re.MULTILINE)


def check_invalid_docstring_section(path: Path, source: str) -> Iterator[Violation]:
    """A docstring section header names a recognized Google section.

    A margin-level line shaped like a section header -- up to three capitalized
    words closing the line with a colon, an indented body beneath -- introduces
    a section, and the house recognizes only the Google set: `Args:`,
    `Returns:`, `Yields:`, `Raises:`, `Note:`, and `Example:` (`Attributes:` is
    recognized too, and left to RS004 to ban). An invented or Sphinx-imported
    header such as `Warns:` or `Design Notes:` hides its body from every rule
    that grades section content -- RS030, RS041, RS043, and RS047 all read it
    as ordinary prose -- so its content belongs in body prose or under a
    recognized header. A header-shaped line with no indented body reads as
    prose -- a list introduction, a fragment -- and is left alone, as is any
    line inside a fenced block.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in internal_walk_docstring_owners(tree):
        constant = internal_docstring_constant(node)
        if constant is None:
            continue
        lines = internal_doc_lines(constant)
        for index in internal_unfenced_margin_lines(lines):
            text = lines[index].text
            if text in InternalSECTION_HEADERS or not _SECTION_SHAPE_PATTERN.match(
                text
            ):
                continue
            if not internal_has_indented_section_body(lines, index):
                continue
            yield Violation(
                lines[index].lineno,
                lines[index].column + 1,
                RS_INVALID_DOCSTRING_SECTION,
                f"'{text}' is not a recognized Google docstring section; use `Args:`, `Returns:`, `Yields:`, `Raises:`, `Note:`, or `Example:`, or fold the content into prose",
            )


_SECTION_SHAPE_PATTERN = re.compile("^[A-Z][A-Za-z]*(?: [A-Z][A-Za-z]*){0,2}:$")


def check_docstring_section_order(path: Path, source: str) -> Iterator[Violation]:
    """Docstring sections follow the canonical Google order.

    The sections with a fixed slot read inputs, then outputs, then failures,
    then the example exercising them: `Args:`, then `Returns:` or `Yields:`,
    then `Raises:`, then `Example:`. A section sitting below one that should
    follow it -- a `Raises:` above the `Returns:` -- is flagged at its own
    header. `Note:` and `Attributes:` hold no fixed slot and never fire.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in internal_walk_docstring_owners(tree):
        constant = internal_docstring_constant(node)
        if constant is None:
            continue
        lines = internal_doc_lines(constant)
        latest_rank = -1
        latest_header = ""
        for index in internal_unfenced_margin_lines(lines):
            line = lines[index]
            rank = _SECTION_RANKS.get(line.text)
            if rank is None:
                continue
            if rank < latest_rank:
                yield Violation(
                    line.lineno,
                    line.column + 1,
                    RS_DOCSTRING_SECTION_ORDER,
                    f"the `{line.text}` section sits below `{latest_header}`; order sections `Args:`, `Returns:`/`Yields:`, `Raises:`, `Example:`",
                )
            else:
                latest_rank, latest_header = (rank, line.text)


_SECTION_RANKS: dict[str, int] = {
    "Args:": 0,
    "Arguments:": 0,
    "Returns:": 1,
    "Return:": 1,
    "Yields:": 1,
    "Yield:": 1,
    "Raises:": 2,
    "Example:": 3,
    "Examples:": 3,
}


def check_docstring_section_alias(path: Path, source: str) -> Iterator[Violation]:
    """A section header uses the canonical Google spelling, not an alias.

    The segmenter accepts `Arguments:`, `Return:`, and `Yield:` so their bodies
    are still graded, but Google's own headers are `Args:`, `Returns:`, and
    `Yields:`, and one spelling per corpus keeps a section greppable. Each
    alias header is flagged and, under `--fix`, rewritten to its canonical form
    in place. `Notes:` and `Examples:` are not aliases: singular versus plural
    there is the author's semantic choice.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in internal_walk_docstring_owners(tree):
        constant = internal_docstring_constant(node)
        if constant is None:
            continue
        for lineno, column, found, canonical in internal_docstring_section_alias_faults(
            constant
        ):
            yield Violation(
                lineno,
                column + 1,
                RS_DOCSTRING_SECTION_ALIAS,
                f"the `{found}` header is an alias of the canonical Google header; write `{canonical}`",
            )


def fix_docstring_section_alias(
    path: Path, source: str, skip_lines: frozenset[int] = frozenset()
) -> str:
    """Rewrites each alias section header to its canonical form, RS058's fix.

    Each header the check flags is replaced in place with its canonical
    spelling; nothing else on the line moves. A header whose line is in
    `skip_lines` is left alone.

    Returns:
        The source with each alias header rewritten, unchanged when nothing
        rewrites.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return source
    source_lines = source.splitlines()
    changed = False
    for node in internal_walk_docstring_owners(tree):
        constant = internal_docstring_constant(node)
        if constant is None:
            continue
        for lineno, column, found, canonical in internal_docstring_section_alias_faults(
            constant
        ):
            if lineno in skip_lines:
                continue
            line = source_lines[lineno - 1]
            offset = line.find(found, column)
            if offset != -1:
                source_lines[lineno - 1] = (
                    line[:offset] + canonical + line[offset + len(found) :]
                )
                changed = True
    return _join_source_lines(source, source_lines) if changed else source
