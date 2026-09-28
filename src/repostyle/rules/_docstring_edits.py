"""Builds safe edits for structured documentation prose."""

from __future__ import annotations

import ast
import io
import re
import tokenize
from collections.abc import Iterator
from pathlib import Path

from repostyle._shared import (
    _LIST_ITEM_PATTERN,
    _join_source_lines,
    _parse_python,
    _terminal_punctuation_fault,
)
from repostyle.rules._docstring_source import (
    InternalBACKTICK_SPAN_PATTERN,
    InternalBulletItem,
    internal_doc_lines,
    internal_docstring_constant,
    internal_docstring_prose_units,
    internal_is_distinctive_code_token,
)
from repostyle.rules._prose_analysis import (
    InternalIDENTIFIER_PATTERN,
)
from repostyle.rules._prose_sources import (
    internal_is_bullet_continuation,
    internal_terminal_insert_index,
    internal_unfenced_margin_lines,
    internal_unfenced_md_lines,
    internal_walk_docstring_owners,
)
from repostyle.rules._prose_units import (
    InternalProseUnit,
)
from repostyle.rules._violation import (
    RS_NO_DOUBLE_BACKTICKS,
    Violation,
)


def internal_blank_outside_docstring(
    line: str, lineno: int, constant: ast.Constant
) -> str:
    """Blanks the parts of a shared physical line outside the docstring.

    A one-line `def` or `class` puts its signature on the same physical line as
    the docstring, and a comment can trail the closing quote, so scanning the
    whole line would read a signature name or a trailing comment as docstring
    prose. Blanking the columns before the literal's start on its first line
    and after its end on its last line to equal-length spaces confines the scan
    to the docstring while keeping every following offset valid.
    """
    start = constant.col_offset if lineno == constant.lineno else 0
    end = constant.end_col_offset if lineno == constant.end_lineno else len(line)
    return " " * start + line[start:end] + " " * (len(line) - end)


def internal_docstring_section_alias_faults(
    constant: ast.Constant,
) -> Iterator[tuple[int, int, str, str]]:
    """Yields `(lineno, column, found, canonical)` for each alias header.

    Only a margin line outside a fenced block is read, the same positions the
    section checks read, so an entry caption or a fence line never yields.
    """
    lines = internal_doc_lines(constant)
    for index in internal_unfenced_margin_lines(lines):
        canonical = InternalSECTION_ALIASES.get(lines[index].text)
        if canonical is not None:
            yield (
                lines[index].lineno,
                lines[index].column,
                lines[index].text,
                canonical,
            )


InternalSECTION_ALIASES: dict[str, str] = {
    "Arguments:": "Args:",
    "Return:": "Returns:",
    "Yield:": "Yields:",
}


def fix_docstring_terminal_punctuation(
    path: Path, source: str, skip_lines: frozenset[int] = frozenset()
) -> str:
    """Appends a period to each unterminated docstring prose unit, RS030's fix.

    A summary, body paragraph, or section entry that the rule flags as missing
    terminal punctuation gains a trailing `.` after its content, before the
    closing quote when the quote shares the line. A unit whose line is in
    `skip_lines` is left untouched.

    Returns:
        The source with a period appended to each flagged unit, unchanged when
        nothing appends.
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
        for unit in internal_docstring_prose_units(constant):
            if unit.kind == "bullet" or unit.lineno in skip_lines:
                continue
            if _terminal_punctuation_fault(unit.text, is_prose=True) != "missing":
                continue
            line = source_lines[unit.lineno - 1]
            index = internal_terminal_insert_index(line, unit.lineno, constant)
            source_lines[unit.lineno - 1] = f"{line[:index]}.{line[index:]}"
            changed = True
    return _join_source_lines(source, source_lines) if changed else source


def internal_backticks_a_code_symbol(units: list[InternalProseUnit]) -> bool:
    """Reports whether a docstring already backticks a code-shaped token.

    A backticked span whose content holds a distinctive identifier is the
    consistency trigger: it shows the author backticks code in this docstring,
    so a bare sibling token is an inconsistency rather than deliberate prose.
    The caller passes only the prose units the bare-token scan reads, so a
    backtick inside a doctest or `Example:` block, which the scan skips, never
    trips the trigger.
    """
    return any(
        internal_is_distinctive_code_token(match.group())
        for unit in units
        for span in InternalBACKTICK_SPAN_PATTERN.finditer(unit.text)
        for match in InternalIDENTIFIER_PATTERN.finditer(span.group().strip("`"))
    )


def internal_check_double_backticks_in_lines(source: str) -> Iterator[Violation]:
    for index, line in internal_unfenced_md_lines(source):
        match = DOUBLE_BACKTICK_PATTERN.search(line)
        if match:
            yield Violation(
                index + 1,
                match.start() + 1,
                RS_NO_DOUBLE_BACKTICKS,
                "use single backticks, not double, in prose",
            )


DOUBLE_BACKTICK_PATTERN = re.compile("(?<!`)``(?!`)")


def internal_comment_bullet_lists(
    block: list[tuple[int, int, str]],
) -> list[list[InternalBulletItem]]:
    """Groups a comment block's bullet lines into the lists RS053 judges.

    A line whose post-hash text opens with a bullet marker starts an item; a
    non-bullet line indented past the list's markers wraps the open item; a
    same-indent bullet continues the list; any other line, or a marker-indent
    change, ends the open list.
    """
    lists: list[list[InternalBulletItem]] = []
    items: list[InternalBulletItem] = []
    open_item: tuple[int, int, list[str]] | None = None
    list_indent = -1
    for lineno, column, string in block:
        indent, text = _comment_body(string)
        is_bullet = _LIST_ITEM_PATTERN.match(text) is not None
        if internal_is_bullet_continuation(
            is_bullet=is_bullet,
            open_item=open_item,
            indent=indent,
            list_indent=list_indent,
        ):
            assert open_item is not None
            open_item[2].append(text)
            continue
        _comment_finish_bullet_item(open_item, items)
        open_item = None
        if _comment_ends_bullet_list(
            is_bullet=is_bullet, items=items, indent=indent, list_indent=list_indent
        ):
            if items:
                lists.append(items)
            items = []
        if is_bullet:
            if not items:
                list_indent = indent
            open_item = (lineno, column + 1, [text])
    _comment_finish_bullet_item(open_item, items)
    if items:
        lists.append(items)
    return lists


def _comment_body(comment: str) -> tuple[int, str]:
    """Splits a comment into its post-hash indent width and stripped text."""
    body = comment.lstrip("#")
    return (len(body) - len(body.lstrip()), body.strip())


def _comment_ends_bullet_list(
    *, is_bullet: bool, items: list[InternalBulletItem], indent: int, list_indent: int
) -> bool:
    """Reports whether a comment line closes the current bullet list."""
    return not is_bullet or bool(items and indent != list_indent)


def _comment_finish_bullet_item(
    open_item: tuple[int, int, list[str]] | None, items: list[InternalBulletItem]
) -> None:
    """Appends an open comment bullet to its current list."""
    if open_item is None:
        return
    marker_line, marker_col, parts = open_item
    items.append(InternalBulletItem(marker_line, marker_col, " ".join(parts)))
    return


def internal_comment_lines(
    source: str,
) -> tuple[dict[int, _StandaloneComment], dict[int, str]]:
    """Splits a source's comments into the standalone and trailing maps.

    Returns:
        The standalone-comment map and the trailing-comment map.
    """
    source_lines = source.splitlines()
    standalone: dict[int, _StandaloneComment] = {}
    trailing: dict[int, str] = {}
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type != tokenize.COMMENT:
                continue
            lineno, column = token.start
            if source_lines[lineno - 1][:column].strip():
                trailing[lineno] = token.string
            else:
                standalone[lineno] = (column, token.string)
    except tokenize.TokenError:
        pass
    return (standalone, trailing)


_StandaloneComment = tuple[int, str]
