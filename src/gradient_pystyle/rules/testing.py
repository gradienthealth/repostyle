"""Test-suite rules: test naming and the mock/patch ban."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

from gradient_pystyle.rules._shared import _parse_python, _posix
from gradient_pystyle.rules._violation import (
    RS_NO_MOCK_PATCH,
    RS_TEST_NAMING,
    Violation,
)

TEST_NAME_PATTERN = re.compile(r"^test_[A-Z][A-Za-z0-9]*_[A-Z][A-Za-z0-9]*$")
FAKES_PATH_FRAGMENT = "tests/fakes/"
UNIT_TEST_PATH_FRAGMENT = "tests/unit/"


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
