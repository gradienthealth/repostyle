"""Duration rule: module-level durations use `timedelta`, not raw seconds."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

from pystyle.rules._shared import _parse_python
from pystyle.rules._violation import RS_DURATION_AS_TIMEDELTA, Violation

SECONDS_CONSTANT_PATTERN = re.compile(r"^_?[A-Z][A-Z0-9_]*_SECONDS$")


def check_duration_as_timedelta(path: Path, source: str) -> Iterator[Violation]:
    """Module-level duration constants must be `timedelta`, not raw seconds.

    Flag module-level assignments whose name matches `*_SECONDS` (with
    an optional leading underscore) and whose value is a numeric
    literal. The convention is `timedelta(seconds=N)`; raw seconds
    constants are reserved for boundaries where the wire format requires
    an integer (DB columns, JSON payloads, external library APIs), and
    those live on settings or domain fields inside class bodies, not at
    module scope.
    """
    tree = _parse_python(path, source)
    if not isinstance(tree, ast.Module):
        return
    for stmt in tree.body:
        targets, value = _assignment_targets_and_value(stmt)
        if value is None:
            continue
        if not isinstance(value, ast.Constant) or not isinstance(
            value.value, int | float
        ):
            continue
        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            if SECONDS_CONSTANT_PATTERN.match(target.id) is None:
                continue
            yield Violation(
                stmt.lineno,
                stmt.col_offset + 1,
                RS_DURATION_AS_TIMEDELTA,
                f"'{target.id}' is a module-level duration; "
                f"use `timedelta(seconds={value.value})` instead",
            )


def _assignment_targets_and_value(
    stmt: ast.stmt,
) -> tuple[list[ast.expr], ast.expr | None]:
    """Return the targets and value of `stmt` if it is an assignment.

    Resolve an `Assign` or `AnnAssign` to its targets and value, and
    return `([], None)` for any other statement.
    """
    if isinstance(stmt, ast.Assign):
        return list(stmt.targets), stmt.value
    if isinstance(stmt, ast.AnnAssign):
        return [stmt.target], stmt.value
    return [], None
