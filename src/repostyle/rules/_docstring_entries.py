"""Parses Google-style docstring entries and prose clauses."""

from __future__ import annotations

import ast
import re

from repostyle.rules._violation import (
    Violation,
)


def internal_entries(
    sections: dict[str | None, list[str]],
    captions: frozenset[str] | set[str],
    pattern: re.Pattern[str],
) -> set[str]:
    """Returns the entry names `pattern` captures under `captions`."""
    return {
        match.group(1)
        for caption in captions
        for line in sections.get(caption, ())
        if (match := pattern.match(line))
    }


def internal_group_by_section(docstring: str) -> dict[str | None, list[str]]:
    """Groups a cleaned docstring's post-summary lines by their section.

    A line before the first Google-style header keys `None`; a later line keys
    the caption of the section it falls under. The summary lines are excluded,
    so the `None` group holds only the body prose after them.
    """
    lines = docstring.splitlines()
    index = 0
    while index < len(lines) and lines[index].strip():
        index += 1
    sections: dict[str | None, list[str]] = {}
    section: str | None = None
    for line in lines[index:]:
        header = _SECTION_HEADER_PATTERN.match(line)
        if header is not None:
            section = header.group(1)
        else:
            sections.setdefault(section, []).append(line)
    return sections


def internal_split_into_clauses(body: str) -> list[str]:
    """Splits docstring body prose into clauses on sentence punctuation.

    Newlines fold to spaces first, so a clause does not shift when the prose is
    rewrapped to a different width. A `.` or `;` ends a clause only outside a
    backtick span -- the dot of a dotted code reference like `pkg.mod.Error`
    stays within its clause rather than fragmenting it -- and a comma never
    does, so a name or verb listed mid-clause is not read as a clause of its
    own. A body with an unbalanced backtick has no well-formed spans to
    protect, so it falls back to a plain punctuation split rather than let one
    stray backtick swallow every sentence boundary after it.
    """
    flowing = body.replace("\n", " ")
    if flowing.count("`") % 2:
        return _SENTENCE_PUNCTUATION.split(flowing)
    clauses: list[str] = []
    current: list[str] = []
    in_span = False
    for char in flowing:
        if char == "`":
            in_span = not in_span
        if char in ".;" and (not in_span):
            clauses.append("".join(current))
            current = []
        else:
            current.append(char)
    clauses.append("".join(current))
    return clauses


_SENTENCE_PUNCTUATION = re.compile("[.;]")


def internal_unstructured_prose(docstring: str) -> str:
    """Returns the summary and body prose before the first section header."""
    lines: list[str] = []
    for line in docstring.splitlines():
        if _SECTION_HEADER_PATTERN.match(line):
            break
        lines.append(line)
    return "\n".join(lines)


_SECTION_HEADER_PATTERN = re.compile(
    "^[ \\t]*(Args|Arguments|Keyword Args|Keyword Arguments|Returns|Yields|Raises|Attributes|Note|Notes|Example|Examples|Warning|Warnings|Todo|See Also|References):\\s*$"
)


def internal_violation(
    node: ast.FunctionDef | ast.AsyncFunctionDef, rule: str, message: str
) -> Violation:
    return Violation(node.lineno, node.col_offset + 1, rule, message)
