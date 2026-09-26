"""Finds documentation prose across Python and Markdown sources."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from functools import lru_cache
from typing import NamedTuple

from repostyle._shared import (
    _comment_text,
    _is_directive_comment,
    _is_prose_comment,
    _walk_tree,
)
from repostyle.rules._violation import (
    RS_SUMMARY_COMMENT_AS_DOCSTRING,
    Violation,
)


def internal_is_bullet_continuation(
    *,
    is_bullet: bool,
    open_item: tuple[int, int, list[str]] | None,
    indent: int,
    list_indent: int,
) -> bool:
    """Reports whether a comment line continues the open bullet item."""
    return not is_bullet and open_item is not None and (indent > list_indent)


def internal_leading_comment_line(
    node: ast.AsyncFunctionDef | ast.ClassDef | ast.FunctionDef,
    comments: dict[int, tuple[int, str]],
    source_lines: list[str],
) -> int | None:
    """Returns the line of the first-position standalone comment in `node`.

    The comment sits directly above the first body statement, with only blank
    lines between, below the definition header. A comment deeper in the body,
    or one trailing the signature, is not returned, so only the leading summary
    position is in scope.
    """
    line = node.body[0].lineno - 1
    while line > node.lineno:
        if line in comments:
            return line
        if not source_lines[line - 1].strip():
            line -= 1
            continue
        return None
    return None


def internal_module_summary_comment(
    tree: ast.Module, comments: dict[int, tuple[int, str]]
) -> Iterator[Violation]:
    """Flags a module whose first prose line is a comment, not a docstring.

    A leading shebang, coding, or tool-directive line is skipped, so the
    summary comment beneath it is still reached; the first non-directive
    standalone comment then decides, since only the leading position is in
    scope.
    """
    if ast.get_docstring(tree, clean=False) is not None:
        return
    first_code = tree.body[0].lineno if tree.body else None
    for line in sorted(comments):
        if first_code is not None and line >= first_code:
            return
        text = _comment_text(comments[line][1])
        if _is_directive_comment(text):
            continue
        if _is_prose_comment(text):
            yield Violation(
                line,
                comments[line][0] + 1,
                RS_SUMMARY_COMMENT_AS_DOCSTRING,
                "leading summary comment should be a module docstring",
            )
        return


def internal_summary_comment_owners(
    tree: ast.Module,
) -> Iterator[ast.AsyncFunctionDef | ast.ClassDef | ast.FunctionDef]:
    """Yields every class and function definition in `tree`."""
    for node in _walk_tree(tree):
        if isinstance(node, ast.AsyncFunctionDef | ast.ClassDef | ast.FunctionDef):
            yield node


def internal_terminal_insert_index(
    line: str, lineno: int, constant: ast.Constant
) -> int:
    """Returns the column on `line` just past a prose unit's last content.

    When the closing quote shares the unit's last line, the index lands before
    it; otherwise it lands after the line's last non-space character.
    """
    stripped = line.rstrip()
    if lineno == constant.end_lineno:
        for delimiter in ('"""', "'''", '"', "'"):
            if stripped.endswith(delimiter):
                return len(stripped[: -len(delimiter)].rstrip())
    return len(stripped)


def internal_terminal_punctuation_message(kind: str) -> str:
    """Returns the fix message for a missing terminal mark on `kind`."""
    subject = {
        "summary": "docstring summary",
        "body": "docstring body paragraph",
        "entry": "section entry",
    }[kind]
    return f"{subject} should end with terminal punctuation (`.`, `!`, or `?`)"


def internal_unfenced_margin_lines(lines: list[InternalDocLine]) -> Iterator[int]:
    """Yields the index of each non-blank margin line outside a fenced block.

    The margin lines are where a section header can sit; a section's body,
    being indented past the margin, never yields, so an entry caption such as
    `ValueError:` is not read as a header.
    """
    in_fence = False
    for index, line in enumerate(lines):
        if line.text.startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence and line.relative_indent == 0 and line.text:
            yield index


class InternalDocLine(NamedTuple):
    lineno: int
    "1-based source line of this docstring line."
    column: int
    "0-based leading-whitespace width, the violation's column anchor."
    relative_indent: int
    "Indent relative to the docstring's body margin, for structure."
    text: str
    "The line stripped of leading and trailing whitespace."


def internal_unfenced_md_lines(source: str) -> Iterator[tuple[int, str]]:
    """Yields `(index, line)` for each line outside a fenced code block."""
    in_fence = False
    for index, line in enumerate(source.splitlines()):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            yield (index, line)


@lru_cache(maxsize=128)
def internal_walk_docstring_owners(
    tree: ast.AST,
) -> tuple[ast.AsyncFunctionDef | ast.ClassDef | ast.FunctionDef | ast.Module, ...]:
    """Returns each node in `tree` able to carry a docstring, in walk order."""
    return tuple(
        node
        for node in _walk_tree(tree)
        if isinstance(
            node, ast.AsyncFunctionDef | ast.ClassDef | ast.FunctionDef | ast.Module
        )
    )
