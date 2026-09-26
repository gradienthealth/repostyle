"""Internal doc-fill implementation partition 4."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator

from repostyle._shared import (
    _walk_tree,
)
from repostyle.rules._doc_fill_impl_5 import (
    InternalParagraphGrouper,
)
from repostyle.rules._doc_fill_impl_7 import (
    InternalFillLine,
)
from repostyle.rules._violation import (
    RS_DOUBLE_SPACE_AFTER_PERIOD,
    Violation,
)


def internal_docstring_double_space_faults(
    tree: ast.Module | None, source_lines: list[str]
) -> Iterator[Violation]:
    """Yields double-space violations from docstring lines."""
    if tree is None:
        return
    for node in _walk_tree(tree):
        if not internal_is_bare_string_literal_statement(node):
            continue
        start = node.value.lineno
        end = node.value.end_lineno or start
        for lineno in range(start, end + 1):
            for match in InternalDOUBLE_SPACE_RE.finditer(source_lines[lineno - 1]):
                yield Violation(
                    lineno,
                    match.start() + 1,
                    RS_DOUBLE_SPACE_AFTER_PERIOD,
                    "double space after sentence-ending punctuation; use a single space",
                )


InternalDOUBLE_SPACE_RE = re.compile("([.!?]) {2,}")


def internal_docstring_fill_lines(
    source_lines: list[str], start: int, end: int
) -> list[InternalFillLine]:
    lines: list[InternalFillLine] = []
    for lineno in range(start + 1, end + 1):
        rendered = source_lines[lineno - 1].rstrip()
        text = rendered.strip()
        if text in ('"""', "'''"):
            continue
        lines.append(
            InternalFillLine(lineno, rendered, len(rendered) - len(text), text)
        )
    return lines


def internal_folded_fill_lines(
    source_lines: list[str], run: tuple[int, ...]
) -> list[InternalFillLine]:
    """Builds the fill lines of one YAML folded-scalar run."""
    lines: list[InternalFillLine] = []
    for lineno in run:
        rendered = source_lines[lineno - 1]
        text = rendered.strip()
        lines.append(
            InternalFillLine(
                lineno, rendered, len(rendered) - len(text), text, is_folded=True
            )
        )
    return lines


def internal_is_bare_string_literal_statement(node: ast.AST) -> bool:
    """Reports whether `node` is a bare string-literal expression statement."""
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def internal_is_folded_prose(lines: list[InternalFillLine]) -> bool:
    """Reports whether a YAML folded-scalar run reads as prose."""
    return lines[-1].text.endswith(_FOLDED_PROSE_TERMINATORS)


_FOLDED_PROSE_TERMINATORS = (".", "!", "?")


def internal_group_paragraphs(
    lines: list[InternalFillLine],
) -> Iterator[list[InternalFillLine]]:
    accumulator = InternalParagraphGrouper()
    for line in lines:
        accumulator.consume(line)
    accumulator.close()
    yield from accumulator.units
