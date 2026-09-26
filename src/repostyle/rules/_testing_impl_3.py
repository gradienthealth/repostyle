"""Internal implementation partition 3."""

from __future__ import annotations

import ast
from functools import cache
from pathlib import Path

from repostyle._shared import (
    _matches_config_glob,
    _parse_python,
    _posix,
    _repostyle_table,
    _string_list,
    find_pyproject,
)
from repostyle.rules._testing_impl_4 import (
    InternalTestFunction,
    internal_restates_content,
)


def internal_is_choreography_call(node: ast.AST) -> bool:
    """Reports whether a node is a `mock.assert_called*`-style call."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and (
            node.func.attr.startswith("assert_called")
            or node.func.attr
            in {"assert_has_calls", "assert_not_called", "assert_any_call"}
        )
    )


def internal_is_in_test_naming_scope(path: Path) -> bool:
    """Reports whether `path` falls in RS002's naming scope.

    The `test-naming-globs` config, when set, replaces the default
    `tests/unit/` path fragment rather than extending it, so a repo states its
    whole test layout in one place.
    """
    pyproject = find_pyproject(path)
    table = _repostyle_table(pyproject)
    if _string_list(table, TEST_NAMING_GLOBS_KEY):
        return _matches_config_glob(path, pyproject, table, TEST_NAMING_GLOBS_KEY)
    return UNIT_TEST_PATH_FRAGMENT in _posix(path)


UNIT_TEST_PATH_FRAGMENT = "tests/unit/"

TEST_NAMING_GLOBS_KEY = "test-naming-globs"


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


def internal_is_mock_decorator(decorator: ast.expr) -> bool:
    """Reports whether a decorator constructs or patches with a mock."""
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    return internal_mock_construct_name(target) is not None


def internal_is_zero_sleep(node: ast.Call) -> bool:
    """Reports whether a sleep call's delay is a literal zero."""
    if not node.args:
        return False
    delay = node.args[0]
    return (
        isinstance(delay, ast.Constant)
        and isinstance(delay.value, int | float)
        and (not isinstance(delay.value, bool))
        and (delay.value == 0)
    )


def internal_mock_construct_name(func: ast.expr) -> str | None:
    """Returns the mock constructor a call target names, or `None`."""
    if isinstance(func, ast.Name):
        return func.id if func.id in MOCK_CONSTRUCTORS else None
    if isinstance(func, ast.Attribute):
        if func.attr in MOCK_CONSTRUCTORS:
            return func.attr
        if isinstance(func.value, ast.Name) and func.value.id in MOCK_CONSTRUCTORS:
            return func.value.id
    return None


MOCK_CONSTRUCTORS = frozenset(
    {"Mock", "MagicMock", "AsyncMock", "NonCallableMock", "patch"}
)


def internal_module_helpers(tree: ast.AST) -> dict[str, InternalTestFunction]:
    """Returns the module-level functions that are not themselves tests."""
    return {
        node.name: node
        for node in getattr(tree, "body", [])
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and (not node.name.startswith("test_"))
    }


def internal_offending_mock_import(node: ast.AST) -> str | None:
    """Returns the rendered forbidden mock import a node makes, or `None`."""
    if isinstance(node, ast.Import):
        return _offending_plain_import(node)
    if isinstance(node, ast.ImportFrom):
        return _offending_from_import(node)
    return None


def _offending_from_import(node: ast.ImportFrom) -> str | None:
    """Returns the rendered forbidden `from` import a node makes, or `None`."""
    if node.module in FORBIDDEN_MOCK_MODULES:
        return f"from {node.module} import ..."
    if node.module == "unittest" and any(alias.name == "mock" for alias in node.names):
        return "from unittest import mock"
    return None


def _offending_plain_import(node: ast.Import) -> str | None:
    """Returns the rendered forbidden plain import a node makes, or `None`."""
    for alias in node.names:
        root = alias.name.split(".", 1)[0]
        if alias.name in FORBIDDEN_MOCK_MODULES or root == "mock":
            return f"import {alias.name}"
    return None


FORBIDDEN_MOCK_MODULES = frozenset({"unittest.mock", "mock"})


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
