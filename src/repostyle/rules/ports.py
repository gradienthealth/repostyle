"""Port-purity rule: a port file may not name a concrete implementation."""

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
from repostyle.rules._violation import RS_PORT_NO_IMPLEMENTATION, Violation

PORT_IMPLEMENTATION_TOKENS: tuple[str, ...] = (
    "bigquery",
    "boto3",
    "httpx",
    "psycopg",
    "sqlalchemy",
)
# An implementation token paired with the word-boundary pattern matching it
_TokenPattern = tuple[str, re.Pattern[str]]
_PORT_TOKEN_PATTERNS: tuple[_TokenPattern, ...] = tuple(
    (token, re.compile(rf"\b{re.escape(token)}\b", re.IGNORECASE))
    for token in PORT_IMPLEMENTATION_TOKENS
)

PORT_PATH_FRAGMENT = "application/ports/"
PORT_PATH_GLOBS_KEY = "port-path-globs"


def check_port_no_implementation(path: Path, source: str) -> Iterator[Violation]:
    """Port files must not name specific implementation libraries.

    Scoped to the `application/ports/` path fragment of a hexagonal layout by
    default, and to `port-path-globs` when a repo sets that key, so a repo
    whose ports sit elsewhere states its own layout.
    """
    if not _is_in_port_scope(path):
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in _walk_tree(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        for token, pattern in _PORT_TOKEN_PATTERNS:
            if pattern.search(node.value):
                yield Violation(
                    node.lineno,
                    node.col_offset + 1,
                    RS_PORT_NO_IMPLEMENTATION,
                    f"port file names '{token}'; describe contract, not implementation",
                )


def _is_in_port_scope(path: Path) -> bool:
    """Reports whether `path` falls in RS006's port scope.

    The `port-path-globs` config, when set, replaces the default
    `application/ports/` path fragment rather than extending it, so a repo
    states its whole port layout in one place.
    """
    pyproject = find_pyproject(path)
    table = _repostyle_table(pyproject)
    if _string_list(table, PORT_PATH_GLOBS_KEY):
        return _matches_config_glob(path, pyproject, table, PORT_PATH_GLOBS_KEY)
    return PORT_PATH_FRAGMENT in _posix(path)
