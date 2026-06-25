"""Helpers shared across rule modules.

A helper used by a single rule lives in that rule's module; one used by
two or more lives here so the rule modules stay independent of each
other.
"""

from __future__ import annotations

import ast
import re
from functools import lru_cache
from pathlib import Path

# A pytest-collected test class: `Test` followed by an uppercase letter
# or the end of the name, so `Testimony` and `Tester` are not matched.
TEST_CLASS_PATTERN = re.compile(r"^Test([A-Z_]|$)")
TEST_FILE_PATTERN = re.compile(r"(^|/)(test_[^/]*|[^/]*_test)\.py$")


def _is_test_file(path: Path) -> bool:
    """Report whether a path is a test module by location or filename."""
    posix = _posix(path)
    return "tests/" in posix or TEST_FILE_PATTERN.search(posix) is not None


def _posix(path: Path) -> str:
    return str(path).replace("\\", "/")


def find_pyproject(start: Path) -> Path | None:
    """Walk up from `start` to find the nearest `pyproject.toml`."""
    start = start.resolve()
    directory = start if start.is_dir() else start.parent
    for candidate in (directory, *directory.parents):
        pyproject = candidate / "pyproject.toml"
        if pyproject.is_file():
            return pyproject
    return None


# Cache on (path, source) so each file is parsed once and its tree
# shared across rules.
@lru_cache(maxsize=128)
def _parse_python(path: Path, source: str) -> ast.AST | None:
    if path.suffix != ".py":
        return None
    try:
        return ast.parse(source)
    except SyntaxError:
        return None
