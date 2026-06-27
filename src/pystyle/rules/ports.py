"""Port-purity rule: a port file may not name a concrete implementation."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

from pystyle.rules._shared import _parse_python, _posix
from pystyle.rules._violation import RS_PORT_NO_IMPLEMENTATION, Violation

PORT_IMPLEMENTATION_TOKENS: tuple[str, ...] = (
    "bigquery",
    "boto3",
    "httpx",
    "psycopg",
    "sqlalchemy",
)
_PORT_TOKEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (token, re.compile(rf"\b{re.escape(token)}\b", re.IGNORECASE))
    for token in PORT_IMPLEMENTATION_TOKENS
)

PORT_PATH_FRAGMENT = "src/fhir_ingestor/application/ports/"


def check_port_no_implementation(path: Path, source: str) -> Iterator[Violation]:
    """Port files must not name specific implementation libraries."""
    if PORT_PATH_FRAGMENT not in _posix(path):
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in ast.walk(tree):
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
