"""Analyzes literal assertions derived from repository files."""

from __future__ import annotations

import ast
from functools import cache
from pathlib import Path

from repostyle._shared import (
    _parse_python,
)
from repostyle.rules._fixture_resolution import (
    InternalTestFunction,
    internal_restates_content,
)


@cache
def internal_parse_conftest(conftest: Path) -> ast.AST | None:
    """Parses a `conftest.py`, or returns `None` when it cannot be read.

    Cached because every test module under a directory resolves through the
    same file, and a lint run reads one snapshot of the tree.
    """
    try:
        source = conftest.read_text(encoding="utf-8")
    except OSError:
        return None
    return _parse_python(conftest, source)


def internal_pins_literals(function: InternalTestFunction) -> bool:
    """Reports whether every comparison a test asserts faces a literal.

    A test qualifies when it asserts at least one comparison and none of them
    weighs one derived value against another, since such a comparison holds two
    places to one agreement rather than restating a single one.
    """
    comparisons = [
        node.test
        for node in ast.walk(function)
        if isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare)
    ]
    return bool(comparisons) and all(
        any(_is_literal(side) for side in (test.left, *test.comparators))
        or all(
            internal_restates_content(side) for side in (test.left, *test.comparators)
        )
        for test in comparisons
    )


def _is_literal(node: ast.AST) -> bool:
    """Reports whether an expression is a literal the source states outright.

    A constant, a negated constant, a collection whose entries are all
    literals, and a bare conversion of one all qualify; anything read from a
    parsed structure does not.
    """
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.UnaryOp):
        return _is_literal(node.operand)
    if isinstance(node, ast.List | ast.Set | ast.Tuple):
        return all(_is_literal(element) for element in node.elts)
    if isinstance(node, ast.Dict):
        keys = [key for key in node.keys if key is not None]
        return all(_is_literal(entry) for entry in (*keys, *node.values))
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and (node.func.id in LITERAL_COLLECTION_BUILTINS)
    ):
        return all(_is_literal(argument) for argument in node.args)
    return False


LITERAL_COLLECTION_BUILTINS = frozenset({"frozenset", "list", "set", "sorted", "tuple"})


def internal_module_helpers(tree: ast.AST) -> dict[str, InternalTestFunction]:
    """Returns the module-level functions that are not themselves tests."""
    return {
        node.name: node
        for node in getattr(tree, "body", [])
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and (not node.name.startswith("test_"))
    }


def internal_quantifies(function: InternalTestFunction) -> bool:
    """Reports whether a test asserts across every entry it read.

    A comprehension or loop in the test's own body states a property that holds
    for each entry, which an edit adding an entry can still break, so it is not
    a restatement of what the file happens to say today.
    """
    return any(isinstance(node, _QUANTIFIERS) for node in ast.walk(function))


_QUANTIFIERS = (
    ast.AsyncFor,
    ast.DictComp,
    ast.For,
    ast.GeneratorExp,
    ast.ListComp,
    ast.SetComp,
)
