"""Helpers shared across rule modules.

A helper used by a single rule lives in that rule's module; one used by
two or more lives here so the rule modules stay independent of each
other.
"""

from __future__ import annotations

import ast
from functools import lru_cache
from pathlib import Path


def _posix(path: Path) -> str:
    return str(path).replace("\\", "/")


# Cache on (path, source) so each file is parsed once and its tree is
# shared across rules instead of re-parsed per rule.
@lru_cache(maxsize=128)
def _parse_python(path: Path, source: str) -> ast.AST | None:
    if path.suffix != ".py":
        return None
    try:
        return ast.parse(source)
    except SyntaxError:
        return None
