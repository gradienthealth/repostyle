"""Inline, block, and whole-file suppression directives.

A `# style: ignore[RS010]` trailing comment drops that one rule's findings on
its line. A `# style: ignore-block[RS010]` comment drops the rule across a
whole statement, from its first decorator through its last body line. A
`# style: ignore-file[RS010]` comment drops it everywhere in the file, wherever
in the file it sits. Each form drops every rule's findings in its scope when
written without a bracket. The token `style` rather than `noqa` keeps these
from colliding with ruff's own suppression handling.

A block directive attaches to the first statement starting on or after its own
line, so it reads either above a definition or trailing the definition's
opening line. It covers its own line alone where no statement follows it, and
in a file with no Python tree to attach to: a TOML, YAML, or shell file, or a
Python file that does not parse.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

from repostyle._comments import extract_comments
from repostyle._shared import _parse_python
from repostyle.rules import Violation

_RULE_LIST = r"(?:\[([\sA-Z0-9,]*)\])?"
_FILE_DIRECTIVE = re.compile(rf"#\s*style:\s*ignore-file\b{_RULE_LIST}")
_BLOCK_DIRECTIVE = re.compile(rf"#\s*style:\s*ignore-block\b{_RULE_LIST}")
_LINE_DIRECTIVE = re.compile(rf"#\s*style:\s*ignore\b(?!-file|-block){_RULE_LIST}")

# A span of source lines a directive covers, as `(start, end, rules)` with both
# bounds inclusive. `rules` of `None` is the unbracketed directive, which
# suppresses every rule; an empty set is `[]`, which suppresses none.
_Span = tuple[int, int, frozenset[str] | None]


def filter_suppressed(
    path: Path, violations: Iterable[Violation], source: str
) -> list[Violation]:
    """Drops violations suppressed by a `# style: ignore` in `source`."""
    suppressions = _parse(path, source)
    return [v for v in violations if not suppressions.suppresses(v.line, v.rule)]


def suppressed_lines(path: Path, source: str, rule: str) -> tuple[bool, frozenset[int]]:
    """Reports whole-file suppression and the lines suppressing `rule`.

    Returns:
        A tuple `(file_suppressed, suppressed)`. `file_suppressed` is whether a
        `# style: ignore-file` directive suppresses `rule` across the entire
        file. `suppressed` is the set of lines on which `rule` is suppressed by
        a line or block directive, whether unbracketed or naming `rule`.
    """
    suppressions = _parse(path, source)
    return (
        suppressions.suppresses_file(rule),
        frozenset(suppressions.lines_suppressing(rule)),
    )


def _parse(path: Path, source: str) -> _Suppressions:
    suppressions = _Suppressions()
    spans = _statement_spans(path, source)
    for comment in extract_comments(path, source):
        file_match = _FILE_DIRECTIVE.search(comment.string)
        if file_match is not None:
            suppressions.add_file(_listed_rules(file_match.group(1)))
            continue
        block_match = _BLOCK_DIRECTIVE.search(comment.string)
        if block_match is not None:
            start, end = _attached_span(spans, comment.lineno)
            suppressions.add_span(start, end, _listed_rules(block_match.group(1)))
            continue
        line_match = _LINE_DIRECTIVE.search(comment.string)
        if line_match is not None:
            suppressions.add_span(
                comment.lineno, comment.lineno, _listed_rules(line_match.group(1))
            )
    return suppressions


def _attached_span(spans: tuple[tuple[int, int], ...], lineno: int) -> tuple[int, int]:
    """Returns the line span a block directive on `lineno` covers.

    Attaches to the first statement starting on or after `lineno`, taking the
    outermost where several start together, so a directive above a decorated
    class covers the class and its methods and one trailing a `def` line covers
    that function. Falls back to `lineno` alone where nothing follows.
    """
    following = [span for span in spans if span[0] >= lineno]
    if not following:
        return lineno, lineno
    start = min(span[0] for span in following)
    return start, max(span[1] for span in following if span[0] == start)


def _listed_rules(listed: str | None) -> frozenset[str] | None:
    """Returns the rules a directive names, `None` where it is unbracketed."""
    if listed is None:
        return None
    return frozenset(rule for rule in listed.replace(" ", "").split(",") if rule)


# Cache on (path, source) alongside the tree and comment scans, so a file's
# spans are walked once and shared across the suppression parses the linter and
# each fixer trigger.
@lru_cache(maxsize=128)
def _statement_spans(path: Path, source: str) -> tuple[tuple[int, int], ...]:
    """Returns the inclusive line span of every statement in `source`.

    A decorated statement's span opens at its first decorator, so a directive
    written above the decorators still covers the definition they wrap. A file
    with no Python tree -- another language, or a Python file that does not
    parse -- has no spans.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return ()
    spans: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.stmt):
            continue
        decorators = getattr(node, "decorator_list", [])
        start = min([node.lineno, *(d.lineno for d in decorators)])
        spans.append((start, node.end_lineno or node.lineno))
    return tuple(sorted(spans))


class _Suppressions:
    """The file, block, and line suppressions parsed from one source."""

    def __init__(self) -> None:
        self._file: list[frozenset[str] | None] = []
        self._spans: list[_Span] = []

    def add_file(self, rules: frozenset[str] | None) -> None:
        """Suppresses the named rules, or all, across the file."""
        self._file.append(rules)

    def add_span(self, start: int, end: int, rules: frozenset[str] | None) -> None:
        """Suppresses the named rules, or all, on lines `start`--`end`."""
        self._spans.append((start, end, rules))

    def lines_suppressing(self, rule: str) -> set[int]:
        """Returns every line a line or block directive suppresses `rule`."""
        return {
            line
            for start, end, rules in self._spans
            if _covers(rules, rule)
            for line in range(start, end + 1)
        }

    def suppresses(self, line: int, rule: str) -> bool:
        """Reports whether `rule` on `line` is suppressed."""
        if self.suppresses_file(rule):
            return True
        return any(
            start <= line <= end and _covers(rules, rule)
            for start, end, rules in self._spans
        )

    def suppresses_file(self, rule: str) -> bool:
        """Reports whether a file directive suppresses `rule` everywhere."""
        return any(_covers(rules, rule) for rules in self._file)


def _covers(listed: frozenset[str] | None, rule: str) -> bool:
    return listed is None or rule in listed
