"""Checks that record classes document each field beside its declaration."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

from repostyle._shared import _parse_python, _walk_tree
from repostyle.rules._doc_value_analysis import (
    internal_describes_field_as_subject,
)
from repostyle.rules._function_contracts import (
    internal_split_docstring,
)
from repostyle.rules._prose_units import (
    internal_field_has_docstring,
    internal_has_dataclass_decorator,
)
from repostyle.rules._violation import (
    RS_FIELD_DESCRIBED_IN_CLASS_DOCSTRING,
    Violation,
)


def check_field_described_in_class_docstring(
    path: Path, source: str
) -> Iterator[Violation]:
    """Flags a record field explained in its class docstring, not beside it.

    A record class fires once per field that has no field docstring of its own
    while the class docstring describes it. Record classes are these:

    - A class decorated as a dataclass or an attrs class.
    - A subclass of `NamedTuple`, `TypedDict`, or pydantic's `BaseModel`.

    The class docstring describes a field through an `Args:` entry naming it or
    a body clause whose subject is the backtick-wrapped field name. Per-field
    detail belongs in the string literal below the field, where a reader finds
    it beside the declaration and an editor shows it on hover. A field the
    class docstring only references, or never mentions, does not fire, and a
    `ClassVar` annotation is not a field. An `Attributes:` block is left to
    RS004.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in _walk_tree(tree):
        if isinstance(node, ast.ClassDef) and _is_record_class(node):
            yield from _fields_described_in_class_docstring(node)


def _fields_described_in_class_docstring(node: ast.ClassDef) -> Iterator[Violation]:
    """Yields a finding per bare field the class docstring describes."""
    docstring = ast.get_docstring(node, clean=True)
    if docstring is None:
        return
    body, documented, _ = internal_split_docstring(docstring)
    for index, stmt in enumerate(node.body):
        name = _field_name(stmt)
        if name is None or internal_field_has_docstring(node.body, index):
            continue
        if name in documented or internal_describes_field_as_subject(body, name):
            yield Violation(
                stmt.lineno,
                stmt.col_offset + 1,
                RS_FIELD_DESCRIBED_IN_CLASS_DOCSTRING,
                f"field '{name}' is described in the docstring of '{node.name}'; move the description into a field docstring below it",
            )


def _field_name(stmt: ast.stmt) -> str | None:
    """Returns the name a class-body statement declares as a field, if any."""
    if not isinstance(stmt, ast.AnnAssign) or not isinstance(stmt.target, ast.Name):
        return None
    annotation = stmt.annotation
    if isinstance(annotation, ast.Subscript):
        annotation = annotation.value
    if _dotted_name(annotation).rpartition(".")[2] == "ClassVar":
        return None
    return stmt.target.id


def _is_record_class(node: ast.ClassDef) -> bool:
    """Reports whether a class declares a record of annotated fields."""
    if internal_has_dataclass_decorator(node):
        return True
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if _dotted_name(target) in _ATTRS_DECORATORS:
            return True
    return any(
        _dotted_name(base).rpartition(".")[2] in _RECORD_BASES for base in node.bases
    )


_ATTRS_DECORATORS = frozenset(
    {
        "attr.attrs",
        "attr.define",
        "attr.frozen",
        "attr.mutable",
        "attr.s",
        "attrs.define",
        "attrs.frozen",
        "attrs.mutable",
        "define",
    }
)

_RECORD_BASES = frozenset({"BaseModel", "NamedTuple", "TypedDict"})


def _dotted_name(node: ast.expr) -> str:
    """Returns the dotted name an attribute chain spells, or `""`."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else ""
    return ""
