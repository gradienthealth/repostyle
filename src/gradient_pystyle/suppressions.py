"""Inline and whole-file suppression directives.

A `# style: ignore[RS010]` trailing comment drops that one rule's
findings on its line; `# style: ignore` (no bracket) drops every rule's
findings on the line; `# style: ignore-file` anywhere drops the whole
file. The token `style` rather than `noqa` keeps these from colliding
with ruff's own suppression handling.
"""

from __future__ import annotations

import io
import re
import tokenize
from collections.abc import Iterable

from gradient_pystyle.rules import Violation

_FILE_DIRECTIVE = re.compile(r"#\s*style:\s*ignore-file\b")
_LINE_DIRECTIVE = re.compile(r"#\s*style:\s*ignore\b(?!-file)(?:\[([\sA-Z0-9,]*)\])?")


class _LineSuppressions:
    """The per-line suppressions parsed from one source's comments."""

    def __init__(self) -> None:
        self._all: set[int] = set()
        self._by_rule: dict[int, set[str]] = {}

    def add_all(self, line: int) -> None:
        """Suppress every rule on `line`."""
        self._all.add(line)

    def add_rules(self, line: int, rules: set[str]) -> None:
        """Suppress the named rules on `line`."""
        self._by_rule.setdefault(line, set()).update(rules)

    def suppresses(self, line: int, rule: str) -> bool:
        """Report whether `rule` on `line` is suppressed."""
        return line in self._all or rule in self._by_rule.get(line, set())

    def lines_waiving(self, rule: str) -> set[int]:
        """Return every line on which `rule` is suppressed."""
        return self._all | {
            line for line, rules in self._by_rule.items() if rule in rules
        }


def _parse(source: str) -> tuple[bool, _LineSuppressions]:
    file_suppressed = False
    lines = _LineSuppressions()
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for token in tokens:
            if token.type != tokenize.COMMENT:
                continue
            if _FILE_DIRECTIVE.search(token.string):
                file_suppressed = True
                continue
            match = _LINE_DIRECTIVE.search(token.string)
            if match is None:
                continue
            listed = match.group(1)
            if listed is None:
                lines.add_all(token.start[0])
            else:
                lines.add_rules(
                    token.start[0], {r for r in listed.replace(" ", "").split(",") if r}
                )
    except tokenize.TokenError:
        pass
    return file_suppressed, lines


def filter_suppressed(violations: Iterable[Violation], source: str) -> list[Violation]:
    """Drop violations waived by a `# style: ignore` directive in `source`."""
    file_suppressed, lines = _parse(source)
    if file_suppressed:
        return []
    return [v for v in violations if not lines.suppresses(v.line, v.rule)]


def suppressed_lines(source: str, rule: str) -> tuple[bool, frozenset[int]]:
    """Report whole-file suppression and the lines waiving `rule`.

    The first element is whether a `# style: ignore-file` directive
    waives the entire file; the second is the set of lines on which
    `rule` is suppressed, whether by an unscoped `# style: ignore` or
    one naming `rule`. An autofixer consults this to leave waived lines
    untouched.
    """
    file_suppressed, lines = _parse(source)
    return file_suppressed, frozenset(lines.lines_waiving(rule))
