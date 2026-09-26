"""Maps docstring text to source lines and prose units."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable
from typing import NamedTuple

from repostyle.rules._prose_sources import (
    InternalDocLine,
)
from repostyle.rules._prose_units import (
    InternalDocstringSegmenter,
    InternalProseUnit,
)


def internal_reads_as_code_reference(name: str, text: str, start: int) -> bool:
    """Reports whether `name` at `start` reads as code rather than English.

    A literal reads as code mid-sentence, but at a sentence start its capital
    could open an English clause, so it is exempt there. Any other name fires
    only when its shape rules out an English word: an underscore, a digit, or
    an interior capital beside a lowercase letter (CamelCase). A plain
    lowercase, Titlecase, or all-caps word could be English and is left alone.
    """
    if name in InternalLITERAL_CONSTANTS:
        return not _begins_sentence(text, start)
    return internal_is_distinctive_code_token(name)


InternalLITERAL_CONSTANTS = frozenset({"None", "True", "False"})


def _begins_sentence(text: str, start: int) -> bool:
    """Reports whether the token at `start` begins `text` or a new sentence."""
    before = text[:start].rstrip()
    return not before or before.endswith(_SENTENCE_ENDINGS)


_SENTENCE_ENDINGS = (".", "!", "?")


def internal_docstring_constant(node: ast.AST) -> ast.Constant | None:
    """Returns the docstring string-literal node of `node`, or `None`."""
    body = getattr(node, "body", None)
    if not body:
        return None
    first = body[0]
    if (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        return first.value
    return None


def internal_docstring_prose_units(constant: ast.Constant) -> list[InternalProseUnit]:
    """Groups a docstring's lines into summary, body, and entry units."""
    segmenter = InternalDocstringSegmenter()
    for line in internal_doc_lines(constant):
        segmenter.consume(line)
    segmenter.close()
    return segmenter.units


def internal_doc_lines(constant: ast.Constant) -> list[InternalDocLine]:
    """Splits a docstring literal into structure-tagged source lines.

    The first line abuts the opening quote, so it anchors its column at the
    literal and the body margin is taken from the first following non-blank
    line, with every later line's indent measured relative to it. The source
    line is clamped to the literal's physical span, so a docstring carrying
    escaped newlines or built by implicit concatenation still points within
    itself rather than past it.
    """
    lines = constant.value.splitlines()
    last = constant.end_lineno or constant.lineno
    margin = next(
        (len(line) - len(line.lstrip()) for line in lines[1:] if line.strip()), 0
    )
    result: list[InternalDocLine] = []
    for index, line in enumerate(lines):
        lineno = min(constant.lineno + index, last)
        column = constant.col_offset if index == 0 else len(line) - len(line.lstrip())
        relative = 0 if index == 0 else max(0, column - margin)
        result.append(InternalDocLine(lineno, column, relative, line.strip()))
    return result


def internal_docstring_summary_line(docstring: str) -> str:
    """Returns the first non-blank line of a cleaned `docstring`, stripped."""
    return next((line.strip() for line in docstring.splitlines() if line.strip()), "")


def internal_first_bare_token(
    source_lines: list[str], linenos: Iterable[int], name: str
) -> tuple[int, int] | None:
    """Finds the first unbackticked `name` on the selected lines.

    Backtick spans are dropped before the search, so a mention already in code
    font is skipped and the position points at the bare token a fix must wrap.

    Returns:
        The 1-based line and column, or `None` when no bare mention exists.
    """
    pattern = re.compile(f"(?<![\\w`]){re.escape(name)}(?![\\w`])")
    for lineno in linenos:
        stripped = InternalBACKTICK_SPAN_PATTERN.sub(" ", source_lines[lineno - 1])
        match = pattern.search(stripped)
        if match is not None:
            return (lineno, match.start() + 1)
    return None


InternalBACKTICK_SPAN_PATTERN = re.compile("`[^`]*`")


def internal_has_indented_section_body(
    lines: list[InternalDocLine], index: int
) -> bool:
    """Reports whether the line at `index` owns an indented section body.

    A section header's body sits indented past the margin on the next non-blank
    line; a header-shaped line followed at the margin, or one ending the
    docstring, is prose rather than a section.
    """
    for line in lines[index + 1 :]:
        if line.text:
            return line.relative_indent > 0
    return False


def internal_is_distinctive_code_token(name: str) -> bool:
    """Reports whether a token's shape rules out an ordinary English word.

    An underscore, a digit, or an interior capital beside a lowercase letter
    (CamelCase) marks a token as code wherever it sits. A plain lowercase,
    Titlecase, or all-caps word could be English and is not distinctive, and
    neither is a pluralized all-caps acronym (`UIDs`, `URLs`), whose only
    lowercase letter is the trailing `s`.
    """
    if "_" in name or any(character.isdigit() for character in name):
        return True
    if _PLURAL_ACRONYM_PATTERN.fullmatch(name):
        return False
    has_interior_capital = any(character.isupper() for character in name[1:])
    return has_interior_capital and any(character.islower() for character in name)


_PLURAL_ACRONYM_PATTERN = re.compile("[A-Z]{2,}s")


class InternalBulletItem(NamedTuple):
    lineno: int
    "1-based source line of the item's bullet marker."
    col: int
    "1-based column the violation points at."
    text: str
    "The item's lines joined into one string, bullet marker included."
