"""Docstring and markdown prose rules: no `Attributes:`, no double backticks."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

from gradient_pystyle.rules._shared import _parse_python
from gradient_pystyle.rules._violation import (
    RS_NO_ATTRIBUTES_BLOCK,
    RS_NO_DOUBLE_BACKTICKS,
    Violation,
)

ATTRIBUTES_SECTION_PATTERN = re.compile(r"^\s*Attributes:\s*$", re.MULTILINE)
DOUBLE_BACKTICK_PATTERN = re.compile(r"(?<!`)``(?!`)")


def _walk_docstring_owners(
    tree: ast.AST,
) -> Iterator[ast.AsyncFunctionDef | ast.ClassDef | ast.FunctionDef | ast.Module]:
    for node in ast.walk(tree):
        if isinstance(
            node, ast.AsyncFunctionDef | ast.ClassDef | ast.FunctionDef | ast.Module
        ):
            yield node


def check_no_attributes_block(path: Path, source: str) -> Iterator[Violation]:
    """Docstrings must not use a Google `Attributes:` block."""
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in _walk_docstring_owners(tree):
        docstring = ast.get_docstring(node, clean=False)
        if docstring is None:
            continue
        if ATTRIBUTES_SECTION_PATTERN.search(docstring) is None:
            continue
        yield Violation(
            getattr(node, "lineno", 1),
            RS_NO_ATTRIBUTES_BLOCK,
            "use per-field attribute docstrings, not a Google `Attributes:` block",
        )


def _check_double_backticks_in_lines(source: str) -> Iterator[Violation]:
    in_fence = False
    for lineno, line in enumerate(source.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if DOUBLE_BACKTICK_PATTERN.search(line):
            yield Violation(
                lineno,
                RS_NO_DOUBLE_BACKTICKS,
                "use single backticks, not double, in prose",
            )


def check_no_double_backticks_in_md(path: Path, source: str) -> Iterator[Violation]:
    """Markdown prose may not use double backticks."""
    if path.suffix != ".md":
        return
    yield from _check_double_backticks_in_lines(source)


def check_no_double_backticks_in_docstrings(
    path: Path, source: str
) -> Iterator[Violation]:
    """Python docstring prose may not use double backticks."""
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in _walk_docstring_owners(tree):
        docstring = ast.get_docstring(node, clean=False)
        if docstring is None:
            continue
        if DOUBLE_BACKTICK_PATTERN.search(docstring):
            yield Violation(
                getattr(node, "lineno", 1),
                RS_NO_DOUBLE_BACKTICKS,
                "use single backticks, not double, in docstrings",
            )
