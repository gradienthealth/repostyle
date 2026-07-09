"""Type-annotation shape rule: warn when a type nests subscripts too deeply.

A subscripted generic buried two deep inside others (`dict[str, tuple[list[int],
str]]`) packs a data structure into a signature that a reader has to unpack in
their head every time they meet it. Past two levels of nesting the annotation is
usually standing in for a type that wants a name — a `TypeAlias`, a
`NamedTuple`, or a dataclass — so the depth is a smell worth a second look
rather than a defect, and the rule warns rather than fails. A single-level
`Iterator[tuple[...]]` or `Callable[..., Iterator[...]]` is idiomatic and left
alone.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

from repostyle.rules._shared import _parse_python
from repostyle.rules._violation import RS_DEEPLY_NESTED_TYPE, Violation

# Two levels of subscripting (`Iterator[tuple[Path, str]]`, `dict[str,
# list[int]]`) is idiomatic and reads at a glance; the warning fires only once a
# third subscript nests inside the second. Every `ast.Subscript` layer counts
# the same — there is no exemption for `tuple` or `Callable`, since a nested
# generic is as hard to read whatever wraps it. A PEP 604 `X | Y` union is an
# `ast.BinOp` rather than a subscript, so it adds no level of its own.
TYPE_NESTING_LIMIT = 2

# The old-style spelling `X: TypeAlias = <type>` puts the aliased type in the
# assignment's value, not its annotation, so the value is inspected when the
# annotation is this marker rather than a real type.
_TYPE_ALIAS_MARKER = "TypeAlias"

# `type X = <type>`, the PEP 695 spelling, parses to this node only on Python
# 3.12+; it is absent from the 3.11 `ast` module, so it is resolved by name and
# skipped where the running interpreter has no such node.
_TYPE_ALIAS_NODE = getattr(ast, "TypeAlias", None)


def check_deeply_nested_type(path: Path, source: str) -> Iterator[Violation]:
    """Flags a type annotation that nests subscripted generics too deeply.

    Every `ast.Subscript` layer counts one level of depth, and an annotation
    nesting them past the limit of two — `list[tuple[int, list[str]]]`,
    `dict[str, tuple[Callable[..., None], ...]]` — is reported at its opening
    node as a warning. The check covers a parameter annotation, a return
    annotation, a variable annotation, and a `TypeAlias` value, in both its
    old-style and PEP 695 spellings. The remedy is to name the buried type as a
    `TypeAlias`, `NamedTuple`, or dataclass and reference the name instead.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    for annotation in _annotation_roots(tree):
        depth = _subscript_depth(annotation)
        if depth > TYPE_NESTING_LIMIT:
            yield Violation(
                annotation.lineno,
                annotation.col_offset + 1,
                RS_DEEPLY_NESTED_TYPE,
                f"type annotation nests subscripts {depth} levels deep; over "
                f"the limit of {TYPE_NESTING_LIMIT}, extract a named type (a "
                "TypeAlias, NamedTuple, or dataclass)",
            )


def _annotation_roots(tree: ast.AST) -> Iterator[ast.expr]:
    """Yields the top-level type expression of each annotated position."""
    for node in ast.walk(tree):
        if isinstance(node, ast.arg) and node.annotation is not None:
            yield node.annotation
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            if node.returns is not None:
                yield node.returns
        elif isinstance(node, ast.AnnAssign):
            root = _alias_value_or_annotation(node)
            if root is not None:
                yield root
        elif _TYPE_ALIAS_NODE is not None and isinstance(node, _TYPE_ALIAS_NODE):
            yield node.value


def _alias_value_or_annotation(node: ast.AnnAssign) -> ast.expr | None:
    """Returns the type an annotated assignment carries, or `None`.

    An `X: TypeAlias = <type>` alias carries its type in the value; every other
    annotated assignment carries it in the annotation. A bare `x: int` with no
    value is still the type in the annotation.
    """
    if _is_type_alias_marker(node.annotation) and node.value is not None:
        return node.value
    return node.annotation


def _is_type_alias_marker(node: ast.expr) -> bool:
    """Reports whether an annotation is the `TypeAlias` marker, plain or dotted."""
    if isinstance(node, ast.Name):
        return node.id == _TYPE_ALIAS_MARKER
    return isinstance(node, ast.Attribute) and node.attr == _TYPE_ALIAS_MARKER


def _subscript_depth(node: ast.AST) -> int:
    """Returns the deepest run of nested `ast.Subscript` nodes in a subtree."""
    deepest_child = max(
        (_subscript_depth(child) for child in ast.iter_child_nodes(node)),
        default=0,
    )
    if isinstance(node, ast.Subscript):
        return deepest_child + 1
    return deepest_child
