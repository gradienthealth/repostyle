"""Test-suite rules: test naming and the mock/patch ban."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

from pystyle.rules._shared import _is_test_file, _parse_python, _posix
from pystyle.rules._violation import (
    RS_BEHAVIOR_VERIFICATION_ONLY,
    RS_CONDITIONAL_TEST_LOGIC,
    RS_EXCESSIVE_MOCKING,
    RS_NO_MOCK_PATCH,
    RS_SLEEPY_TEST,
    RS_TEST_NAMING,
    Violation,
)

TEST_NAME_PATTERN = re.compile(r"^test_[A-Z][A-Za-z0-9]*_[A-Z][A-Za-z0-9]*$")
FAKES_PATH_FRAGMENT = "tests/fakes/"
UNIT_TEST_PATH_FRAGMENT = "tests/unit/"
SLEEP_MODULES = frozenset({"time", "asyncio"})
MOCK_CONSTRUCTORS = frozenset(
    {"Mock", "MagicMock", "AsyncMock", "NonCallableMock", "patch"}
)
EXCESSIVE_MOCK_LIMIT = 3
_BRANCH_STATEMENTS = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try)


def check_test_naming(path: Path, source: str) -> Iterator[Violation]:
    """Tests under tests/unit/ must follow `test_StateUnderTest_ExpectedBehavior`."""
    if UNIT_TEST_PATH_FRAGMENT not in _posix(path):
        return
    if path.name in {"conftest.py", "__init__.py"}:
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if not node.name.startswith("test_"):
            continue
        if TEST_NAME_PATTERN.match(node.name):
            continue
        yield Violation(
            node.lineno,
            node.col_offset + 1,
            RS_TEST_NAMING,
            f"test '{node.name}' must match `test_StateUnderTest_ExpectedBehavior`",
        )


def check_no_mock_patch(path: Path, source: str) -> Iterator[Violation]:
    """`unittest.mock` and `mock` imports are rejected outside tests/fakes/."""
    if FAKES_PATH_FRAGMENT in _posix(path):
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    forbidden_modules = {"unittest.mock", "mock"}
    for node in ast.walk(tree):
        offending: str | None = None
        lineno = 0
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if alias.name in forbidden_modules or root == "mock":
                    offending = f"import {alias.name}"
                    lineno = node.lineno
                    break
        elif isinstance(node, ast.ImportFrom):
            if node.module in forbidden_modules:
                offending = f"from {node.module} import ..."
                lineno = node.lineno
            elif node.module == "unittest" and any(
                alias.name == "mock" for alias in node.names
            ):
                offending = "from unittest import mock"
                lineno = node.lineno
        if offending is None:
            continue
        yield Violation(
            lineno,
            node.col_offset + 1,
            RS_NO_MOCK_PATCH,
            f"`{offending}` rejected; use a port fake under tests/fakes/",
        )


def _test_functions(
    tree: ast.AST,
) -> Iterator[ast.AsyncFunctionDef | ast.FunctionDef]:
    """Yield the `test`-prefixed functions pytest would collect."""
    for node in ast.walk(tree):
        if isinstance(
            node, ast.FunctionDef | ast.AsyncFunctionDef
        ) and node.name.startswith("test"):
            yield node


def _branch_asserts_directly(node: ast.stmt) -> bool:
    bodies: list[list[ast.stmt]] = [node.body, getattr(node, "orelse", [])]
    if isinstance(node, ast.Try):
        bodies.append(node.finalbody)
        bodies.extend(handler.body for handler in node.handlers)
    return any(isinstance(stmt, ast.Assert) for body in bodies for stmt in body)


def _mock_construct_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id if func.id in MOCK_CONSTRUCTORS else None
    if isinstance(func, ast.Attribute):
        if func.attr in MOCK_CONSTRUCTORS:
            return func.attr
        if isinstance(func.value, ast.Name) and func.value.id in MOCK_CONSTRUCTORS:
            return func.value.id
    return None


def _is_mock_decorator(decorator: ast.expr) -> bool:
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    return _mock_construct_name(target) is not None


def _is_choreography_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and (
            node.func.attr.startswith("assert_called")
            or node.func.attr
            in {"assert_has_calls", "assert_not_called", "assert_any_call"}
        )
    )


def check_conditional_test_logic(path: Path, source: str) -> Iterator[Violation]:
    """A test may not wrap an `assert` in conditional or loop logic.

    An `if`, `for`, `while`, or `try` whose own body asserts makes the
    asserted path depend on runtime state, so a test that never enters
    the branch passes vacuously. Keep test bodies straight-line, or
    split the cases into separate tests or parametrized rows.
    """
    if not _is_test_file(path):
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    for function in _test_functions(tree):
        for node in ast.walk(function):
            if isinstance(node, _BRANCH_STATEMENTS) and _branch_asserts_directly(node):
                yield Violation(
                    node.lineno,
                    node.col_offset + 1,
                    RS_CONDITIONAL_TEST_LOGIC,
                    f"test '{function.name}' wraps an `assert` in control flow; "
                    f"keep the asserted path straight-line",
                )


def check_sleepy_test(path: Path, source: str) -> Iterator[Violation]:
    """A test may not call `time.sleep` or `asyncio.sleep`.

    A real sleep makes the suite slow and couples it to wall-clock
    timing, the usual source of flakes; wait on the observable condition
    or drive a fake clock instead.
    """
    if not _is_test_file(path):
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    for function in _test_functions(tree):
        for node in ast.walk(function):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "sleep"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in SLEEP_MODULES
            ):
                yield Violation(
                    node.lineno,
                    node.col_offset + 1,
                    RS_SLEEPY_TEST,
                    f"`{node.func.value.id}.sleep(...)` in a test is slow and "
                    f"flaky; wait on a condition or use a fake clock",
                )


def check_excessive_mocking(path: Path, source: str) -> Iterator[Violation]:
    """Warn when a test builds many mock objects.

    A high mock count per test points at over-mocked, brittle coupling
    worth a look; it is a density signal of where to look, not a verdict
    that any single mock is wrong. Counts `Mock`/`MagicMock`/`patch` and
    their kin, including `@patch` decorators.
    """
    if not _is_test_file(path):
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    for function in _test_functions(tree):
        count = sum(
            1 for decorator in function.decorator_list if _is_mock_decorator(decorator)
        )
        for statement in function.body:
            for node in ast.walk(statement):
                if isinstance(node, ast.Call) and _mock_construct_name(node.func):
                    count += 1
        if count > EXCESSIVE_MOCK_LIMIT:
            yield Violation(
                function.lineno,
                function.col_offset + 1,
                RS_EXCESSIVE_MOCKING,
                f"test '{function.name}' builds {count} mocks; over "
                f"{EXCESSIVE_MOCK_LIMIT} marks where to look, not that any one "
                f"mock is wrong",
            )


def check_behavior_verification_only(path: Path, source: str) -> Iterator[Violation]:
    """Warn when a test asserts only call choreography, never state.

    A test whose only checks are `mock.assert_called*` pins how the unit
    calls its collaborators rather than the outcome a caller relies on,
    so it survives a correct refactor and breaks on a harmless one. A
    test with at least one plain `assert` is left alone.
    """
    if not _is_test_file(path):
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    for function in _test_functions(tree):
        nodes = [node for statement in function.body for node in ast.walk(statement)]
        asserts_state = any(isinstance(node, ast.Assert) for node in nodes)
        asserts_calls = any(_is_choreography_call(node) for node in nodes)
        if asserts_calls and not asserts_state:
            yield Violation(
                function.lineno,
                function.col_offset + 1,
                RS_BEHAVIOR_VERIFICATION_ONLY,
                f"test '{function.name}' asserts only call choreography, not "
                f"observable state",
            )
