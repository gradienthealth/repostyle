"""Resolves names reached through test helpers and pytest fixtures."""

from __future__ import annotations

import ast
from collections.abc import Iterator

from repostyle._shared import (
    _walk_tree,
)


def internal_reached_names(
    function: InternalTestFunction,
    owner: str,
    scopes: dict[tuple[str, str], InternalTestFunction],
    helpers: dict[str, InternalTestFunction],
    seen: set[str] | None = None,
    *,
    should_resolve_fixtures: bool = True,
) -> set[str] | None:
    """Returns every name a test reaches through its fixtures and helpers.

    Resolution is `None` when any fixture on the path is undefined in this
    module, since what it supplies cannot be known from this file alone. A
    module helper is expanded by name only: its parameters are ordinary
    arguments its callers pass, not fixtures pytest resolves.
    """
    seen = set() if seen is None else seen
    names = internal_referenced_names(function)
    for name in sorted(names & helpers.keys() - seen):
        seen.add(name)
        reached = internal_reached_names(
            helpers[name], owner, scopes, helpers, seen, should_resolve_fixtures=False
        )
        if reached is None:
            return None
        names |= reached
    if not should_resolve_fixtures:
        return names
    requested = _requested_fixtures(function, owner, scopes)
    if requested is None:
        return None
    for fixture in requested:
        if fixture.name in seen:
            continue
        seen.add(fixture.name)
        reached = internal_reached_names(fixture, owner, scopes, helpers, seen)
        if reached is None:
            return None
        names |= reached
    return names


def internal_referenced_names(node: ast.AST) -> set[str]:
    """Returns the names and attributes an expression or body references."""
    names: set[str] = set()
    for inner in ast.walk(node):
        if isinstance(inner, ast.Name):
            names.add(inner.id)
        elif isinstance(inner, ast.Attribute):
            names.add(inner.attr)
    return names


def _requested_fixtures(
    function: InternalTestFunction,
    owner: str,
    scopes: dict[tuple[str, str], InternalTestFunction],
) -> list[InternalTestFunction] | None:
    """Returns the fixtures a definition requests, or `None` if one is foreign.

    A parameter resolves against the holding class first and the module next,
    matching how pytest shadows a fixture; one that neither scope defines comes
    from `conftest.py` or from pytest itself and can supply anything.
    """
    arguments = function.args
    requested: list[InternalTestFunction] = []
    for argument in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs):
        if argument.arg in _SELF_ARGUMENTS or argument.arg in INERT_PYTEST_FIXTURES:
            continue
        fixture = scopes.get((owner, argument.arg)) or scopes.get(("", argument.arg))
        if fixture is None:
            return None
        requested.append(fixture)
    return requested


INERT_PYTEST_FIXTURES = frozenset(
    {
        "capfd",
        "capfdbinary",
        "caplog",
        "capsys",
        "capsysbinary",
        "monkeypatch",
        "recwarn",
        "tmp_path",
        "tmp_path_factory",
        "tmpdir",
        "tmpdir_factory",
    }
)

_SELF_ARGUMENTS = frozenset({"cls", "self"})


def internal_restates_content(operand: ast.expr) -> bool:
    """Reports whether an operand carries a string the parsed file supplied.

    A string indexing into the structure names where to look, so it is
    excluded; a string anywhere else in the operand is the file's own content
    quoted back, which is what an ordering or membership check compares.
    """
    keys = _subscript_key_ids(operand)
    return any(
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and (id(node) not in keys)
        for node in ast.walk(operand)
    )


def internal_scoped_functions(
    tree: ast.AST,
) -> Iterator[tuple[str, InternalTestFunction]]:
    """Yields every function beside the name of the class that holds it.

    A function defined at module level takes the empty string, so the two
    scopes pytest resolves a fixture through share one key space.
    """
    for node in _walk_tree(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for member in node.body:
            if isinstance(member, ast.FunctionDef | ast.AsyncFunctionDef):
                yield (node.name, member)
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            yield ("", node)


InternalTestFunction = ast.AsyncFunctionDef | ast.FunctionDef


def _subscript_key_ids(node: ast.AST) -> set[int]:
    """Returns the identities of the constants used as subscript keys."""
    return {
        id(inner)
        for outer in ast.walk(node)
        if isinstance(outer, ast.Subscript)
        for inner in ast.walk(outer.slice)
        if isinstance(inner, ast.Constant)
    }


def internal_test_functions(
    tree: ast.AST,
) -> Iterator[ast.AsyncFunctionDef | ast.FunctionDef]:
    """Yields the `test`-prefixed functions and methods defined in the tree."""
    for node in _walk_tree(tree):
        if isinstance(
            node, ast.FunctionDef | ast.AsyncFunctionDef
        ) and node.name.startswith("test"):
            yield node
