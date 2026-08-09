"""Equality rule: `__eq__` and `__hash__` are defined as a pair, or neither.

Defining `__eq__` without `__hash__` makes instances silently unhashable --
Python sets `__hash__` to `None` on a class that overrides `__eq__` -- and
defining `__hash__` without `__eq__` splits a value hash from identity
equality. The eq-without-hash half is a stand-in for ruff's `PLW1641`
(`eq-without-hash`), which is preview-gated in the pinned ruff version and so
cannot be selected without turning on `preview` globally for every consuming
repo, exactly the `PLR0917`/RS027 situation. When `PLW1641` graduates to
stable, select it in `ruff-base.toml` and drop the eq-without-hash half of this
rule.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

from repostyle._shared import _parse_python
from repostyle.rules._violation import RS_EQ_HASH_PAIRING, Violation

# A class decorated with one of these synthesizes both `__eq__` and `__hash__`
# per its own `eq=`/`frozen=` flags, so a hand-written half is neither missing
# nor a bug; the dataclass and attrs entry points both appear here.
_SYNTHESIZING_DECORATORS = frozenset(
    {"dataclass", "define", "attrs", "attrib", "frozen", "mutable", "s"}
)


def check_eq_hash_pairing(path: Path, source: str) -> Iterator[Violation]:
    """Flags a class defining exactly one of `__eq__` and `__hash__`.

    A class that overrides `__eq__` without also defining `__hash__` is made
    unhashable, since Python sets its `__hash__` to `None`; a class defining
    `__hash__` without `__eq__` keeps a value hash beside identity equality.
    Either half alone is flagged so the two stay a pair. A `@dataclass` or
    `attrs` class is exempt, since the decorator synthesizes both. A class that
    sets `__hash__ = None` is stating the unhashable intent explicitly and is
    left alone, and a class defining `__hash__` alone while subclassing a base
    other than `object` is exempt too, since it may inherit `__eq__` from that
    base -- a relationship an AST check cannot resolve. The eq-without-hash
    half always fires regardless of bases, because overriding `__eq__` nulls
    `__hash__` whatever a base defined.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            yield from _pairing_violation(node)


def _pairing_violation(node: ast.ClassDef) -> Iterator[Violation]:
    """Yields the pairing violation a class earns, if any."""
    if _has_synthesizing_decorator(node):
        return
    defined = _defined_dunders(node)
    has_eq = "__eq__" in defined
    has_hash = "__hash__" in defined
    if has_eq and not has_hash:
        yield Violation(
            node.lineno,
            node.col_offset + 1,
            RS_EQ_HASH_PAIRING,
            f"class '{node.name}' defines `__eq__` but not `__hash__`; Python "
            f"sets `__hash__` to None, making instances unhashable -- define "
            f"`__hash__` too, or set `__hash__ = None` to opt out explicitly",
        )
    elif has_hash and not has_eq and not _has_non_object_base(node):
        yield Violation(
            node.lineno,
            node.col_offset + 1,
            RS_EQ_HASH_PAIRING,
            f"class '{node.name}' defines `__hash__` but not `__eq__`; define "
            f"`__eq__` too so equality and hashing agree",
        )


def _defined_dunders(node: ast.ClassDef) -> set[str]:
    """Returns the `__eq__`/`__hash__` names a class body binds directly.

    A name counts whether bound by a method definition or by a plain assignment
    (`__hash__ = None`), since either puts the name in the class namespace and
    drives Python's hashability decision.
    """
    names: set[str] = set()
    for stmt in node.body:
        if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef):
            names.add(stmt.name)
        elif isinstance(stmt, ast.Assign):
            names.update(
                target.id for target in stmt.targets if isinstance(target, ast.Name)
            )
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            names.add(stmt.target.id)
    return {name for name in names if name in ("__eq__", "__hash__")}


def _has_non_object_base(node: ast.ClassDef) -> bool:
    """Reports whether a class subclasses anything other than `object`.

    A base other than `object` may itself define `__eq__`, so a class defining
    only `__hash__` could be inheriting the equality half rather than omitting
    it.
    """
    return any(
        not (isinstance(base, ast.Name) and base.id == "object") for base in node.bases
    )


def _has_synthesizing_decorator(node: ast.ClassDef) -> bool:
    """Reports whether a class carries a dataclass or attrs decorator.

    Matches the bare (`@dataclass`), dotted (`@dataclasses.dataclass`,
    `@attrs.define`), and called (`@dataclass(frozen=True)`) forms by their
    final name.
    """
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        name = target.id if isinstance(target, ast.Name) else None
        if isinstance(target, ast.Attribute):
            name = target.attr
        if name in _SYNTHESIZING_DECORATORS:
            return True
    return False
