"""Internal docstring-rule implementation partition 2."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

from repostyle._comments import COMMENT_SUFFIXES, extract_comments
from repostyle._shared import (
    _join_source_lines,
    _parse_python,
)
from repostyle.rules._docstrings_impl_3 import (
    internal_docstring_prose_line_numbers,
    internal_glued_code_span_columns,
)
from repostyle.rules._docstrings_impl_7 import (
    DOUBLE_BACKTICK_PATTERN,
    InternalSECTION_ALIASES,
    internal_check_double_backticks_in_lines,
)
from repostyle.rules._docstrings_impl_9 import (
    internal_doc_lines,
    internal_docstring_constant,
)
from repostyle.rules._docstrings_impl_10 import (
    InternalSECTION_HEADERS,
)
from repostyle.rules._docstrings_impl_11 import (
    internal_unfenced_margin_lines,
    internal_unfenced_md_lines,
    internal_walk_docstring_owners,
)
from repostyle.rules._violation import (
    RS_DUPLICATE_DOCSTRING_SECTION,
    RS_GLUED_CODE_SPAN,
    RS_NO_DOUBLE_BACKTICKS,
    Violation,
)


def check_duplicate_docstring_section(path: Path, source: str) -> Iterator[Violation]:
    """A docstring holds at most one section per family.

    A second `Args:`, `Returns:`, or `Raises:` -- under the same spelling or an
    alias, an `Args:` after an `Arguments:` -- splits one section's content
    across two places, so a reader stops at the first and misses the rest. The
    duplicate is flagged at its own header; the fix is to merge its entries
    into the first.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in internal_walk_docstring_owners(tree):
        constant = internal_docstring_constant(node)
        if constant is None:
            continue
        lines = internal_doc_lines(constant)
        first_headers: dict[str, str] = {}
        for index in internal_unfenced_margin_lines(lines):
            line = lines[index]
            family = _SECTION_FAMILIES.get(line.text)
            if family is None:
                continue
            if family in first_headers:
                yield Violation(
                    line.lineno,
                    line.column + 1,
                    RS_DUPLICATE_DOCSTRING_SECTION,
                    f"a second `{line.text}` section duplicates the earlier `{first_headers[family]}`; merge its entries into the first",
                )
            else:
                first_headers[family] = line.text


_SECTION_FAMILIES: dict[str, str] = {
    header: InternalSECTION_ALIASES.get(header, header)
    for header in InternalSECTION_HEADERS
} | {"Notes:": "Note:", "Examples:": "Example:"}


def check_no_double_backticks_in_md(path: Path, source: str) -> Iterator[Violation]:
    """Markdown prose may not use double backticks."""
    if path.suffix != ".md":
        return
    yield from internal_check_double_backticks_in_lines(source)


def check_no_double_backticks_in_docstrings(
    path: Path, source: str
) -> Iterator[Violation]:
    """Python docstring prose may not use double backticks."""
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in internal_walk_docstring_owners(tree):
        docstring = ast.get_docstring(node, clean=False)
        if docstring is None:
            continue
        if DOUBLE_BACKTICK_PATTERN.search(docstring):
            yield Violation(
                getattr(node, "lineno", 1),
                getattr(node, "col_offset", 0) + 1,
                RS_NO_DOUBLE_BACKTICKS,
                "use single backticks, not double, in docstrings",
            )


def fix_double_backticks(
    path: Path, source: str, skip_lines: frozenset[int] = frozenset()
) -> str:
    """Rewrites double backticks to single in `source`, the RS005 fix.

    A markdown file's prose lines and a Python file's docstring lines are
    rewritten; a fenced markdown block and a docstring whose owner line is in
    `skip_lines` are left untouched.

    Returns:
        The source with double backticks rewritten to single, unchanged when
        nothing rewrites.
    """
    if path.suffix == ".md":
        return _fix_double_backticks_md(source)
    tree = _parse_python(path, source)
    if tree is None:
        return source
    source_lines = source.splitlines()
    changed = False
    for node in internal_walk_docstring_owners(tree):
        constant = internal_docstring_constant(node)
        if constant is None or getattr(node, "lineno", 1) in skip_lines:
            continue
        end = constant.end_lineno or constant.lineno
        for lineno in range(constant.lineno, end + 1):
            rewritten = DOUBLE_BACKTICK_PATTERN.sub("`", source_lines[lineno - 1])
            if rewritten != source_lines[lineno - 1]:
                source_lines[lineno - 1] = rewritten
                changed = True
    return _join_source_lines(source, source_lines) if changed else source


def _fix_double_backticks_md(source: str) -> str:
    """Rewrites double backticks to single in a markdown file's prose."""
    source_lines = source.splitlines()
    changed = False
    for index, line in internal_unfenced_md_lines(source):
        rewritten = DOUBLE_BACKTICK_PATTERN.sub("`", line)
        if rewritten != line:
            source_lines[index] = rewritten
            changed = True
    return _join_source_lines(source, source_lines) if changed else source


def check_glued_code_span_in_docstrings(path: Path, source: str) -> Iterator[Violation]:
    """Docstring prose may not glue an inflection to a code span.

    A code span sets a name in code font, so an English suffix run straight
    onto its closing backtick -- a possessive apostrophe-s, a plural, or a verb
    ending -- reads as part of the identifier and breaks the span in rendered
    Markdown. The check fires on a closing backtick followed at once by a
    letter or an apostrophe, and leaves a hyphenated compound such as `-safe`
    alone, since that keeps the span ending on a word boundary. The rule warns
    and has no automatic fix; the remedy is to move the suffix outside the
    span.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    source_lines = source.splitlines()
    for node in internal_walk_docstring_owners(tree):
        constant = internal_docstring_constant(node)
        if constant is None:
            continue
        start = constant.lineno
        end = constant.end_lineno or start
        concatenated = constant.value.count("\n") < end - start
        prose_lines = internal_docstring_prose_line_numbers(constant)
        block = "\n".join(
            (
                line if concatenated or lineno in prose_lines else " " * len(line)
                for lineno, line in enumerate(source_lines[start - 1 : end], start)
            )
        )
        for offset in internal_glued_code_span_columns(block):
            before = block[:offset]
            yield Violation(
                start + before.count("\n"),
                offset - before.rfind("\n"),
                RS_GLUED_CODE_SPAN,
                _GLUED_SPAN_MESSAGE,
            )


def check_glued_code_span_in_comments(path: Path, source: str) -> Iterator[Violation]:
    """A comment may not glue an English suffix onto a code span.

    The same rule the docstring check applies holds for a comment: a suffix run
    onto a code span's closing backtick reads as part of the identifier. A
    standalone and a trailing comment are covered alike, across the Python,
    TOML, YAML, and shell comments `extract_comments` handles -- tokenizing a
    non-Python file as Python here would raise on its first irregular indent.
    """
    if path.suffix not in COMMENT_SUFFIXES:
        return
    for comment in extract_comments(path, source):
        for offset in internal_glued_code_span_columns(comment.string):
            yield Violation(
                comment.lineno,
                comment.column + offset + 1,
                RS_GLUED_CODE_SPAN,
                _GLUED_SPAN_MESSAGE,
            )


def check_glued_code_span_in_md(path: Path, source: str) -> Iterator[Violation]:
    """Markdown prose may not glue an inflection to a code span."""
    if path.suffix != ".md":
        return
    for index, line in internal_unfenced_md_lines(source):
        for offset in internal_glued_code_span_columns(line):
            yield Violation(
                index + 1, offset + 1, RS_GLUED_CODE_SPAN, _GLUED_SPAN_MESSAGE
            )


_GLUED_SPAN_MESSAGE = (
    "a code span carries a glued suffix; move the suffix outside the backticks"
)
