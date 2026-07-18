"""Inline and whole-file suppression directives.

A `# style: ignore[RS010]` trailing comment drops that one rule's findings on
its line; `# style: ignore` (no bracket) drops every rule's findings on the
line; `# style: ignore-file` anywhere drops the whole file. The token `style`
rather than `noqa` keeps these from colliding with ruff's own suppression
handling.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

from repostyle._comments import extract_comments
from repostyle.rules import Violation

_FILE_DIRECTIVE = re.compile(r"#\s*style:\s*ignore-file\b")
_LINE_DIRECTIVE = re.compile(r"#\s*style:\s*ignore\b(?!-file)(?:\[([\sA-Z0-9,]*)\])?")


def filter_suppressed(
    path: Path, violations: Iterable[Violation], source: str
) -> list[Violation]:
    """Drops violations suppressed by a `# style: ignore` in `source`."""
    file_suppressed, lines = _parse(path, source)
    if file_suppressed:
        return []
    return [v for v in violations if not lines.suppresses(v.line, v.rule)]


def suppressed_lines(path: Path, source: str, rule: str) -> tuple[bool, frozenset[int]]:
    """Reports whole-file suppression and the lines suppressing `rule`.

    Returns:
        A tuple `(file_suppressed, suppressed)`. `file_suppressed` is whether a
        `# style: ignore-file` directive suppresses the entire file.
        `suppressed` is the set of lines on which `rule` is suppressed, whether
        by an unscoped `# style: ignore` or one naming `rule`.
    """
    file_suppressed, lines = _parse(path, source)
    return file_suppressed, frozenset(lines.lines_suppressing(rule))


def _parse(path: Path, source: str) -> tuple[bool, _LineSuppressions]:
    file_suppressed = False
    lines = _LineSuppressions()
    for comment in extract_comments(path, source):
        if _FILE_DIRECTIVE.search(comment.string):
            file_suppressed = True
            continue
        match = _LINE_DIRECTIVE.search(comment.string)
        if match is None:
            continue
        listed = match.group(1)
        if listed is None:
            lines.add_all(comment.lineno)
        else:
            lines.add_rules(
                comment.lineno, {r for r in listed.replace(" ", "").split(",") if r}
            )
    return file_suppressed, lines


class _LineSuppressions:
    """The per-line suppressions parsed from one source's comments."""

    def __init__(self) -> None:
        self._all: set[int] = set()
        self._by_rule: dict[int, set[str]] = {}

    def add_all(self, line: int) -> None:
        """Suppresses every rule on `line`."""
        self._all.add(line)

    def add_rules(self, line: int, rules: set[str]) -> None:
        """Suppresses the named rules on `line`."""
        self._by_rule.setdefault(line, set()).update(rules)

    def lines_suppressing(self, rule: str) -> set[int]:
        """Returns every line on which `rule` is suppressed."""
        return self._all | {
            line for line, rules in self._by_rule.items() if rule in rules
        }

    def suppresses(self, line: int, rule: str) -> bool:
        """Reports whether `rule` on `line` is suppressed."""
        return line in self._all or rule in self._by_rule.get(line, set())
