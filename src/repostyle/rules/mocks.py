"""Rules that discourage mock-heavy tests."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

from repostyle._shared import _is_test_file, _parse_python, _posix, _walk_tree
from repostyle.rules._fixture_resolution import internal_test_functions
from repostyle.rules._violation import (
    RS_BEHAVIOR_VERIFICATION_ONLY,
    RS_EXCESSIVE_MOCKING,
    RS_NO_MOCK_PATCH,
    Violation,
)

EXCESSIVE_MOCK_LIMIT = 3
FAKES_PATH_FRAGMENT = "tests/fakes/"
FORBIDDEN_MOCK_MODULES = frozenset({"unittest.mock", "mock"})
MOCK_CONSTRUCTORS = frozenset(
    {"Mock", "MagicMock", "AsyncMock", "NonCallableMock", "patch"}
)


def check_no_mock_patch(path: Path, source: str) -> Iterator[Violation]:
    """Rejects mock-library imports outside the fake implementation tree."""
    if FAKES_PATH_FRAGMENT in _posix(path):
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in _walk_tree(tree):
        offending = _offending_mock_import(node)
        if offending is None:
            continue
        yield Violation(
            node.lineno,
            node.col_offset + 1,
            RS_NO_MOCK_PATCH,
            f"`{offending}` rejected; use a port fake under tests/fakes/",
        )


def check_excessive_mocking(path: Path, source: str) -> Iterator[Violation]:
    """Warns when a test builds many mock objects."""
    if not _is_test_file(path):
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    for function in internal_test_functions(tree):
        count = sum(1 for item in function.decorator_list if _is_mock_decorator(item))
        count += sum(
            1
            for statement in function.body
            for node in ast.walk(statement)
            if isinstance(node, ast.Call) and _mock_construct_name(node.func)
        )
        if count > EXCESSIVE_MOCK_LIMIT:
            yield Violation(
                function.lineno,
                function.col_offset + 1,
                RS_EXCESSIVE_MOCKING,
                f"test '{function.name}' builds {count} mocks; over {EXCESSIVE_MOCK_LIMIT} marks where to look, not that any one mock is wrong",
            )


def check_behavior_verification_only(path: Path, source: str) -> Iterator[Violation]:
    """Warns when a test asserts call choreography but no observable state."""
    if not _is_test_file(path):
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    for function in internal_test_functions(tree):
        nodes = [node for statement in function.body for node in ast.walk(statement)]
        if any(_is_choreography_call(node) for node in nodes) and not any(
            isinstance(node, ast.Assert) for node in nodes
        ):
            yield Violation(
                function.lineno,
                function.col_offset + 1,
                RS_BEHAVIOR_VERIFICATION_ONLY,
                f"test '{function.name}' asserts only call choreography, not observable state",
            )


def _is_choreography_call(node: ast.AST) -> bool:
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


def _is_mock_decorator(decorator: ast.expr) -> bool:
    """Reports whether a decorator constructs or patches with a mock."""
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    return _mock_construct_name(target) is not None


def _mock_construct_name(function: ast.expr) -> str | None:
    """Returns the mock constructor a call target names, or `None`."""
    if isinstance(function, ast.Name):
        return function.id if function.id in MOCK_CONSTRUCTORS else None
    if isinstance(function, ast.Attribute):
        if function.attr in MOCK_CONSTRUCTORS:
            return function.attr
        if (
            isinstance(function.value, ast.Name)
            and function.value.id in MOCK_CONSTRUCTORS
        ):
            return function.value.id
    return None


def _offending_mock_import(node: ast.AST) -> str | None:
    """Returns the forbidden mock import a node makes, or `None`."""
    if isinstance(node, ast.ImportFrom):
        if node.module in FORBIDDEN_MOCK_MODULES:
            return f"from {node.module} import ..."
        if node.module == "unittest" and any(
            alias.name == "mock" for alias in node.names
        ):
            return "from unittest import mock"
    if isinstance(node, ast.Import):
        for alias in node.names:
            if (
                alias.name in FORBIDDEN_MOCK_MODULES
                or alias.name.split(".", 1)[0] == "mock"
            ):
                return f"import {alias.name}"
    return None
