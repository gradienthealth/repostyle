"""Rules for docstring presence and opening sentences."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from repostyle._shared import (
    _comment_text,
    _is_prose_comment,
    _parse_python,
    _repostyle_table,
    _string_list,
    find_pyproject,
)
from repostyle.rules._doc_blocks import internal_doc_blocks
from repostyle.rules._docstring_edits import (
    internal_comment_lines,
)
from repostyle.rules._prose_analysis import (
    internal_dataclass_classes,
)
from repostyle.rules._prose_sources import (
    internal_leading_comment_line,
    internal_module_summary_comment,
    internal_summary_comment_owners,
)
from repostyle.rules._prose_units import (
    internal_field_has_docstring,
)
from repostyle.rules._violation import (
    RS_FIELD_COMMENT_AS_DOCSTRING,
    RS_FILLER_DOCSTRING_OPENING,
    RS_IMPERATIVE_DOCSTRING_OPENING,
    RS_SUMMARY_COMMENT_AS_DOCSTRING,
    Violation,
)
from repostyle.rules.imperative_verbs import (
    IMPERATIVE_OPENING_PATTERN,
    IMPERATIVE_VERB_CONJUGATIONS,
    IMPERATIVE_VERBS,
    conjugate,
)


def check_summary_comment_as_docstring(path: Path, source: str) -> Iterator[Violation]:
    """A leading summary comment should be a docstring.

    A module, class, or function with no docstring whose first body position is
    a standalone prose comment carries a summary that this package's own
    docstring-content rules cannot see; move it into the docstring slot.
    """
    tree = _parse_python(path, source)
    if not isinstance(tree, ast.Module):
        return
    comments, _ = internal_comment_lines(source)
    source_lines = source.splitlines()
    yield from internal_module_summary_comment(tree, comments)
    for node in internal_summary_comment_owners(tree):
        if ast.get_docstring(node, clean=False) is not None or not node.body:
            continue
        line = internal_leading_comment_line(node, comments, source_lines)
        if line is None:
            continue
        column, text = comments[line]
        if not _is_prose_comment(_comment_text(text)):
            continue
        yield Violation(
            line,
            column + 1,
            RS_SUMMARY_COMMENT_AS_DOCSTRING,
            "leading summary comment should be a docstring",
        )


def check_field_comment_as_docstring(path: Path, source: str) -> Iterator[Violation]:
    """A dataclass field comment should be a field docstring.

    A field documented with a trailing prose comment and no following
    string-literal field docstring should carry that text as the per-field
    docstring the house style prefers.
    """
    tree = _parse_python(path, source)
    if not isinstance(tree, ast.Module):
        return
    _, trailing = internal_comment_lines(source)
    for node in internal_dataclass_classes(tree):
        for index, stmt in enumerate(node.body):
            if not isinstance(stmt, ast.AnnAssign):
                continue
            comment = trailing.get(stmt.end_lineno or stmt.lineno)
            if comment is None or not _is_prose_comment(_comment_text(comment)):
                continue
            if internal_field_has_docstring(node.body, index):
                continue
            yield Violation(
                stmt.lineno,
                stmt.col_offset + 1,
                RS_FIELD_COMMENT_AS_DOCSTRING,
                "document a dataclass field with a string-literal docstring below it, not a trailing comment",
            )


def check_filler_docstring_opening(path: Path, source: str) -> Iterator[Violation]:
    """A docstring or Javadoc summary may not open with a filler phrase.

    A summary's first words name what the unit does. An opening like `This
    function`, `Helper to`, `Used to`, `Simply`, or `Just` restates the
    identifier or hedges instead.
    """
    for block in internal_doc_blocks(path, source):
        if _FILLER_OPENING_PATTERN.match(block.summary):
            yield Violation(
                block.lineno,
                block.col,
                RS_FILLER_DOCSTRING_OPENING,
                "docstring opening restates the identifier; state the contract instead",
            )


_FILLER_OPENING_PATTERN = re.compile(
    "^(this (function|method|class|module)\\b|helper (to|for)\\b|used to\\b|simply\\b|just\\b)",
    re.IGNORECASE,
)


def check_imperative_docstring_opening(path: Path, source: str) -> Iterator[Violation]:
    """A docstring or Javadoc summary opens descriptively, not imperatively.

    The house states a unit's own contract in the third person
    (`Returns the lease.`), not as a command (`Return the lease.`), as Google's
    Python and Java style guides both write it, rather than following PEP 257's
    imperative recommendation. A summary whose first word is a known
    bare-infinitive verb should conjugate it to third-person singular. A repo
    tunes the verb set for its own domain via `imperative-verbs-extra` and
    `imperative-verbs-exclude` in `[tool.repostyle]`.
    """
    pyproject = find_pyproject(path)
    conjugations = _effective_conjugations(pyproject)
    pattern = _effective_pattern(pyproject)
    for block in internal_doc_blocks(path, source):
        match = pattern.match(block.summary)
        if match is None:
            continue
        verb = match.group(1)
        yield Violation(
            block.lineno,
            block.col,
            RS_IMPERATIVE_DOCSTRING_OPENING,
            f"docstring opens in imperative mood; use '{conjugations[verb]}', not '{verb}'",
        )


@lru_cache(maxsize=128)
def _effective_pattern(pyproject: Path | None) -> re.Pattern[str]:
    r"""Returns the opening-verb regex built from this repo's effective verbs.

    Each verb is escaped before joining: `imperative-verbs-extra` comes from
    repo config, not this module's own hardcoded list, so a configured entry
    containing a regex metacharacter must match itself literally rather than be
    interpreted as one. An empty effective verb set (every verb excluded)
    compiles to a pattern that matches nothing, not one that matches everything
    -- `re.compile("^()\\\\b")` would otherwise match the empty string at the
    start of every summary.
    """
    conjugations = _effective_conjugations(pyproject)
    if conjugations is IMPERATIVE_VERB_CONJUGATIONS:
        return IMPERATIVE_OPENING_PATTERN
    if not conjugations:
        return re.compile("(?!)")
    escaped = (re.escape(verb) for verb in conjugations)
    return re.compile("^(" + "|".join(escaped) + ")\\b")


@lru_cache(maxsize=128)
def _effective_conjugations(pyproject: Path | None) -> dict[str, str]:
    """Returns the verb-to-conjugation map, adjusted for this repo's config.

    A repo adds its own survey-backed verb via `imperative-verbs-extra`, or
    drops a homograph too risky for its own domain via
    `imperative-verbs-exclude`, tuning RS034 locally instead of editing the
    shared verb list every repo inherits -- the same override pattern RS017's
    `banned-imports` and RS033's `filename-extensions` already use. A consuming
    repo excluding every verb (its own plus any extra) is left with an empty
    map.
    """
    table = _repostyle_table(pyproject)
    extra = _string_list(table, "imperative-verbs-extra")
    exclude = frozenset(_string_list(table, "imperative-verbs-exclude"))
    if not extra and (not exclude):
        return IMPERATIVE_VERB_CONJUGATIONS
    verbs = dict.fromkeys(
        verb for verb in (*IMPERATIVE_VERBS, *extra) if verb not in exclude
    )
    return {verb: conjugate(verb) for verb in verbs}
