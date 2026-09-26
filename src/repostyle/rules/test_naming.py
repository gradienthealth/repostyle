"""Test-function naming rules."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

from repostyle._shared import (
    _matches_config_glob,
    _parse_python,
    _posix,
    _repostyle_table,
    _string_list,
    _walk_tree,
    find_pyproject,
)
from repostyle.rules._violation import RS_TEST_NAMING, Violation

TEST_NAME_PATTERN = re.compile("^test_[A-Z][A-Za-z0-9]*_[A-Z][A-Za-z0-9]*$")
TEST_NAMING_GLOBS_KEY = "test-naming-globs"
UNIT_TEST_PATH_FRAGMENT = "tests/unit/"


def check_test_naming(path: Path, source: str) -> Iterator[Violation]:
    """Requires a unit test to match the house naming convention."""
    if not _is_in_test_naming_scope(path):
        return
    if path.name in {"conftest.py", "__init__.py"}:
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in _walk_tree(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if not node.name.startswith("test_") or TEST_NAME_PATTERN.match(node.name):
            continue
        yield Violation(
            node.lineno,
            node.col_offset + 1,
            RS_TEST_NAMING,
            f"test '{node.name}' must match `test_StateUnderTest_ExpectedBehavior`",
        )


def _is_in_test_naming_scope(path: Path) -> bool:
    """Reports whether `path` falls in the test-naming scope."""
    pyproject = find_pyproject(path)
    table = _repostyle_table(pyproject)
    if _string_list(table, TEST_NAMING_GLOBS_KEY):
        return _matches_config_glob(path, pyproject, table, TEST_NAMING_GLOBS_KEY)
    return UNIT_TEST_PATH_FRAGMENT in _posix(path)
