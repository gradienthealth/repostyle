"""Internal implementation partition 1."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

from repostyle._shared import (
    _is_test_file,
    _parse_python,
    _posix,
    _walk_tree,
)
from repostyle.rules._testing_impl_2 import (
    internal_branch_asserts_directly,
)
from repostyle.rules._testing_impl_3 import (
    internal_is_choreography_call,
    internal_is_in_test_naming_scope,
    internal_is_mock_decorator,
    internal_is_zero_sleep,
    internal_mock_construct_name,
    internal_offending_mock_import,
)
from repostyle.rules._testing_impl_4 import (
    internal_test_functions,
)
from repostyle.rules._violation import (
    RS_BEHAVIOR_VERIFICATION_ONLY,
    RS_CONDITIONAL_TEST_LOGIC,
    RS_EXCESSIVE_MOCKING,
    RS_NO_MOCK_PATCH,
    RS_SLEEPY_TEST,
    RS_TEST_NAMING,
    Violation,
)


def check_test_naming(path: Path, source: str) -> Iterator[Violation]:
    """A unit test matches `test_StateUnderTest_ExpectedBehavior`.

    Applies to files under `tests/unit/`, or, when the config sets
    `test-naming-globs`, to the files matching those globs instead, so a repo
    keeping its unit tests elsewhere can still hold them to the naming.
    `conftest.py` and `__init__.py` are exempt in either scope.
    """
    if not internal_is_in_test_naming_scope(path):
        return
    if path.name in {"conftest.py", "__init__.py"}:
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in _walk_tree(tree):
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


TEST_NAME_PATTERN = re.compile("^test_[A-Z][A-Za-z0-9]*_[A-Z][A-Za-z0-9]*$")


def check_no_mock_patch(path: Path, source: str) -> Iterator[Violation]:
    """`unittest.mock` and `mock` imports are rejected outside tests/fakes/."""
    if FAKES_PATH_FRAGMENT in _posix(path):
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in _walk_tree(tree):
        offending = internal_offending_mock_import(node)
        if offending is None:
            continue
        yield Violation(
            node.lineno,
            node.col_offset + 1,
            RS_NO_MOCK_PATCH,
            f"`{offending}` rejected; use a port fake under tests/fakes/",
        )


FAKES_PATH_FRAGMENT = "tests/fakes/"


def check_conditional_test_logic(path: Path, source: str) -> Iterator[Violation]:
    """A test may not wrap an `assert` in conditional or loop logic.

    An `if`, `for`, `while`, or `try` whose own body asserts makes the asserted
    path depend on runtime state, so a test that never enters the branch passes
    vacuously. Keep test bodies straight-line, or split the cases into separate
    tests or parametrized rows.
    """
    if not _is_test_file(path):
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    for function in internal_test_functions(tree):
        for node in ast.walk(function):
            if isinstance(
                node, _BRANCH_STATEMENTS
            ) and internal_branch_asserts_directly(node):
                yield Violation(
                    node.lineno,
                    node.col_offset + 1,
                    RS_CONDITIONAL_TEST_LOGIC,
                    f"test '{function.name}' wraps an `assert` in control flow; keep the asserted path straight-line",
                )


_BRANCH_STATEMENTS = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try)


def check_sleepy_test(path: Path, source: str) -> Iterator[Violation]:
    """A test may not call `time.sleep` or `asyncio.sleep`.

    A real sleep makes the suite slow and couples it to wall-clock timing, the
    usual source of flakes; wait on the observable condition or drive a fake
    clock instead. A literal `sleep(0)` is exempt: it is the idiomatic
    single-turn yield to the event loop, neither slow nor flaky.
    """
    if not _is_test_file(path):
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    for function in internal_test_functions(tree):
        for node in ast.walk(function):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and (node.func.attr == "sleep")
                and isinstance(node.func.value, ast.Name)
                and (node.func.value.id in SLEEP_MODULES)
                and (not internal_is_zero_sleep(node))
            ):
                yield Violation(
                    node.lineno,
                    node.col_offset + 1,
                    RS_SLEEPY_TEST,
                    f"`{node.func.value.id}.sleep(...)` in a test is slow and flaky; wait on a condition or use a fake clock",
                )


SLEEP_MODULES = frozenset({"time", "asyncio"})


def check_excessive_mocking(path: Path, source: str) -> Iterator[Violation]:
    """Warns when a test builds many mock objects.

    The rule marks tests that may bind a unit to too many collaborators. The
    count prompts review but does not prescribe a change. The rule counts
    `Mock`, `MagicMock`, `patch`, related constructors, and `@patch`
    decorators.
    """
    if not _is_test_file(path):
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    for function in internal_test_functions(tree):
        count = sum(
            1
            for decorator in function.decorator_list
            if internal_is_mock_decorator(decorator)
        )
        for statement in function.body:
            for node in ast.walk(statement):
                if isinstance(node, ast.Call) and internal_mock_construct_name(
                    node.func
                ):
                    count += 1
        if count > EXCESSIVE_MOCK_LIMIT:
            yield Violation(
                function.lineno,
                function.col_offset + 1,
                RS_EXCESSIVE_MOCKING,
                f"test '{function.name}' builds {count} mocks; over {EXCESSIVE_MOCK_LIMIT} marks where to look, not that any one mock is wrong",
            )


EXCESSIVE_MOCK_LIMIT = 3


def check_behavior_verification_only(path: Path, source: str) -> Iterator[Violation]:
    """Warns when a test asserts only call choreography, never state.

    A test whose only checks are `mock.assert_called*` pins collaborator calls
    instead of a caller-visible outcome. A test with at least one plain
    `assert` is left alone, but that exemption does not make the test useful.
    """
    if not _is_test_file(path):
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    for function in internal_test_functions(tree):
        nodes = [node for statement in function.body for node in ast.walk(statement)]
        asserts_state = any(isinstance(node, ast.Assert) for node in nodes)
        asserts_calls = any(internal_is_choreography_call(node) for node in nodes)
        if asserts_calls and (not asserts_state):
            yield Violation(
                function.lineno,
                function.col_offset + 1,
                RS_BEHAVIOR_VERIFICATION_ONLY,
                f"test '{function.name}' asserts only call choreography, not observable state",
            )
