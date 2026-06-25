"""Resolve the enabled-rule set from config and lint paths with it."""

from __future__ import annotations

import tomllib
from collections.abc import Iterable
from pathlib import Path

from pystyle.rules import (
    ALL_RULE_IDS,
    RS_DOC_FILL,
    Violation,
    reflow_doc_fill,
    run_rule,
)
from pystyle.rules._shared import find_pyproject
from pystyle.suppressions import filter_suppressed, suppressed_lines


def resolve_enabled_rules_for_paths(paths: Iterable[Path]) -> set[str]:
    """Discover config from the first path's directory and resolve rules."""
    paths = list(paths)
    if not paths:
        return set(ALL_RULE_IDS)
    pyproject = find_pyproject(paths[0])
    config = load_config(pyproject) if pyproject is not None else None
    return resolve_enabled_rules(config)


def load_config(pyproject: Path) -> dict | None:
    """Read the `[tool.pystyle]` table from a pyproject file."""
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    return data.get("tool", {}).get("pystyle")


def resolve_enabled_rules(config: dict | None) -> set[str]:
    """Resolve enabled rule ids from a `[tool.pystyle]` table.

    `select` defaults to every rule; `ignore` defaults to none. The
    enabled set is `select` minus `ignore`. A missing or empty table
    enables all rules. An unknown id in `select` or `ignore` raises
    `ValueError`: silently dropping it could resolve `select` to the
    empty set and make the linter pass everything.
    """
    if not config:
        return set(ALL_RULE_IDS)
    known = set(ALL_RULE_IDS)
    select = config.get("select")
    ignore = config.get("ignore", [])
    unknown = (set(select or ()) | set(ignore)) - known
    if unknown:
        raise ValueError(
            "unknown pystyle rule id(s): "
            f"{', '.join(sorted(unknown))}. Known ids: {', '.join(sorted(known))}."
        )
    selected = set(select) if select else known
    return selected - set(ignore)


def lint_paths(paths: Iterable[Path], enabled: set[str]) -> list[Violation]:
    return [v for path in paths for v in lint_path(path, enabled)]


def lint_path(path: Path, enabled: set[str]) -> list[Violation]:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    violations: list[Violation] = []
    for rule_id in enabled:
        violations.extend(run_rule(rule_id, path, source))
    if path.suffix == ".py":
        violations = filter_suppressed(violations, source)
    return sorted(set(violations))


def fix_path(path: Path, enabled: set[str]) -> bool:
    """Reflow RS009 findings in `path` in place, reporting whether it changed.

    A no-op unless RS009 is enabled and `path` is a Python file. A
    whole-file ignore directive leaves the file untouched, and a
    per-line suppression leaves its unit untouched.
    """
    if RS_DOC_FILL not in enabled or path.suffix != ".py":
        return False
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    file_suppressed, skip = suppressed_lines(source, RS_DOC_FILL)
    if file_suppressed:
        return False
    rewritten = reflow_doc_fill(path, source, skip)
    if rewritten == source:
        return False
    path.write_text(rewritten, encoding="utf-8")
    return True
