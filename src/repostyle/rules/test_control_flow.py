"""Rules that keep tests deterministic and straight-line."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

from repostyle._shared import _is_test_file, _parse_python
from repostyle.rules._fixture_resolution import internal_test_functions
from repostyle.rules._violation import (
    RS_CONDITIONAL_TEST_LOGIC,
    RS_SLEEPY_TEST,
    Violation,
)

SLEEP_MODULES = frozenset({"time", "asyncio"})
_BRANCH_STATEMENTS = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try)


def check_conditional_test_logic(path: Path, source: str) -> Iterator[Violation]:
    """Rejects an assertion wrapped in test control flow."""
    if not _is_test_file(path):
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    for function in internal_test_functions(tree):
        for node in ast.walk(function):
            if isinstance(node, _BRANCH_STATEMENTS) and _branch_asserts_directly(node):
                yield Violation(
                    node.lineno,
                    node.col_offset + 1,
                    RS_CONDITIONAL_TEST_LOGIC,
                    f"test '{function.name}' wraps an `assert` in control flow; keep the asserted path straight-line",
                )


def check_sleepy_test(path: Path, source: str) -> Iterator[Violation]:
    """Rejects a nonzero real sleep in a test."""
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
                and node.func.attr == "sleep"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in SLEEP_MODULES
                and not _is_zero_sleep(node)
            ):
                yield Violation(
                    node.lineno,
                    node.col_offset + 1,
                    RS_SLEEPY_TEST,
                    f"`{node.func.value.id}.sleep(...)` in a test is slow and flaky; wait on a condition or use a fake clock",
                )


def _branch_asserts_directly(node: ast.stmt) -> bool:
    """Reports whether a branch or loop statement asserts in its own body."""
    bodies: list[list[ast.stmt]] = [node.body, getattr(node, "orelse", [])]
    if isinstance(node, ast.Try):
        bodies.append(node.finalbody)
        bodies.extend(handler.body for handler in node.handlers)
    return any(isinstance(stmt, ast.Assert) for body in bodies for stmt in body)


def _is_zero_sleep(node: ast.Call) -> bool:
    """Reports whether a sleep call's delay is a literal zero."""
    if not node.args:
        return False
    delay = node.args[0]
    return (
        isinstance(delay, ast.Constant)
        and isinstance(delay.value, int | float)
        and not isinstance(delay.value, bool)
        and delay.value == 0
    )
