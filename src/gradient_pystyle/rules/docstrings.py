"""Docstring and markdown prose rules.

The placement rules move a summary that documents a unit into the
docstring slot ruff D401 grades, and reject docstring openings that
restate the identifier instead of stating the contract: no `Attributes:`
block, no double backticks, no leading summary comment, no field comment
standing in for a field docstring, and no filler opening.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from collections.abc import Iterator
from pathlib import Path

from gradient_pystyle.rules._shared import _parse_python
from gradient_pystyle.rules._violation import (
    RS_FIELD_COMMENT_AS_DOCSTRING,
    RS_FILLER_DOCSTRING_OPENING,
    RS_NO_ATTRIBUTES_BLOCK,
    RS_NO_DOUBLE_BACKTICKS,
    RS_SUMMARY_COMMENT_AS_DOCSTRING,
    Violation,
)

ATTRIBUTES_SECTION_PATTERN = re.compile(r"^\s*Attributes:\s*$", re.MULTILINE)
DOUBLE_BACKTICK_PATTERN = re.compile(r"(?<!`)``(?!`)")

# A comment whose first token after the hash marks it as machinery, not
# prose. The shebang `#!` leads a module; the rest are tool directives a
# docstring must not swallow. Named distinctly from doc_fill's own
# directive pattern, whose membership it deliberately does not share.
_DIRECTIVE_COMMENT_PATTERN = re.compile(
    r"^[ \t]*(!|type:|style:|noqa|pragma|pylint:|mypy:|ruff:|isort:|fmt:)",
)
# A PEP 263 encoding declaration, in either the plain `coding:` form or
# the Emacs `-*- coding: ... -*-` form, anywhere in the comment.
_CODING_DECLARATION_PATTERN = re.compile(r"coding[:=]\s*[-\w.]+")
# A docstring opening that names the unit's category or hedges instead
# of stating its contract. Matched case-insensitively against the
# summary's first non-blank line.
_FILLER_OPENING_PATTERN = re.compile(
    r"^(this (function|method|class|module)\b|helper (to|for)\b|used to\b"
    r"|simply\b|just\b)",
    re.IGNORECASE,
)


def _walk_docstring_owners(
    tree: ast.AST,
) -> Iterator[ast.AsyncFunctionDef | ast.ClassDef | ast.FunctionDef | ast.Module]:
    for node in ast.walk(tree):
        if isinstance(
            node, ast.AsyncFunctionDef | ast.ClassDef | ast.FunctionDef | ast.Module
        ):
            yield node


def check_no_attributes_block(path: Path, source: str) -> Iterator[Violation]:
    """Docstrings must not use a Google `Attributes:` block."""
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in _walk_docstring_owners(tree):
        docstring = ast.get_docstring(node, clean=False)
        if docstring is None:
            continue
        if ATTRIBUTES_SECTION_PATTERN.search(docstring) is None:
            continue
        yield Violation(
            getattr(node, "lineno", 1),
            getattr(node, "col_offset", 0) + 1,
            RS_NO_ATTRIBUTES_BLOCK,
            "use per-field attribute docstrings, not a Google `Attributes:` block",
        )


def _check_double_backticks_in_lines(source: str) -> Iterator[Violation]:
    in_fence = False
    for lineno, line in enumerate(source.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = DOUBLE_BACKTICK_PATTERN.search(line)
        if match:
            yield Violation(
                lineno,
                match.start() + 1,
                RS_NO_DOUBLE_BACKTICKS,
                "use single backticks, not double, in prose",
            )


def check_no_double_backticks_in_md(path: Path, source: str) -> Iterator[Violation]:
    """Markdown prose may not use double backticks."""
    if path.suffix != ".md":
        return
    yield from _check_double_backticks_in_lines(source)


def check_no_double_backticks_in_docstrings(
    path: Path, source: str
) -> Iterator[Violation]:
    """Python docstring prose may not use double backticks."""
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in _walk_docstring_owners(tree):
        docstring = ast.get_docstring(node, clean=False)
        if docstring is None:
            continue
        if DOUBLE_BACKTICK_PATTERN.search(docstring):
            yield Violation(
                getattr(node, "lineno", 1),
                getattr(node, "col_offset", 0) + 1,
                RS_NO_DOUBLE_BACKTICKS,
                "use single backticks, not double, in docstrings",
            )


def _comment_text(comment: str) -> str:
    """Return a comment's prose, stripped of its leading hashes and space."""
    return comment.lstrip("#").strip()


def _is_directive_comment(text: str) -> bool:
    """Report whether a comment's text is a tool directive or coding line."""
    return bool(
        _DIRECTIVE_COMMENT_PATTERN.match(text)
        or _CODING_DECLARATION_PATTERN.search(text)
    )


def _is_code_fragment(text: str) -> bool:
    """Report whether a comment's text parses as commented-out Python.

    A fragment that parses to anything other than a bare expression of a
    name, attribute, comparison, or boolean operation is code: an
    assignment, import, call, or keyword statement. The excluded
    expression shapes are the ones an English sentence parses into —
    `Cache is empty` is a comparison, not a statement worth preserving —
    so prose phrased around `is`, `in`, `and`, or `or` is not mistaken
    for code. The boundary is conservative by design: text that does not
    parse at all is prose, and the rare sentence parsing to another
    shape falls to code, so the rule under-fires rather than over-fires.
    """
    try:
        parsed = ast.parse(text)
    except (SyntaxError, ValueError):
        return False
    if len(parsed.body) != 1 or not isinstance(parsed.body[0], ast.Expr):
        return True
    return not isinstance(
        parsed.body[0].value, ast.Name | ast.Attribute | ast.Compare | ast.BoolOp
    )


def _is_prose_comment(text: str) -> bool:
    """Report whether a comment's text reads as a documenting sentence.

    Prose is capitalised and at least three words. A tool directive, a
    shebang, a coding line, and a commented-out statement are all
    excluded, so the check fires only on a sentence a docstring should
    carry.
    """
    if _is_directive_comment(text):
        return False
    if not text[:1].isupper() or len(text.split()) < 3:
        return False
    return not _is_code_fragment(text)


def _comment_lines(source: str) -> tuple[dict[int, tuple[int, str]], dict[int, str]]:
    """Split a source's comments into the standalone and trailing maps.

    The first map keys each whole-line comment's line to its column and
    text; the second keys each line whose comment trails code to that
    comment's text. A comment is standalone when nothing but whitespace
    precedes it on its line.
    """
    source_lines = source.splitlines()
    standalone: dict[int, tuple[int, str]] = {}
    trailing: dict[int, str] = {}
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type != tokenize.COMMENT:
                continue
            lineno, column = token.start
            if source_lines[lineno - 1][:column].strip():
                trailing[lineno] = token.string
            else:
                standalone[lineno] = (column, token.string)
    except tokenize.TokenError:
        pass
    return standalone, trailing


def _summary_comment_owners(
    tree: ast.Module,
) -> Iterator[ast.AsyncFunctionDef | ast.ClassDef | ast.FunctionDef]:
    """Yield every class and function definition in `tree`."""
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef | ast.ClassDef | ast.FunctionDef):
            yield node


def _leading_comment_line(
    node: ast.AsyncFunctionDef | ast.ClassDef | ast.FunctionDef,
    comments: dict[int, tuple[int, str]],
    source_lines: list[str],
) -> int | None:
    """Return the line of `node`'s first-body-position standalone comment.

    The comment sits directly above the first body statement, with only
    blank lines between, below the definition header. A comment deeper
    in the body, or one trailing the signature, is not returned, so only
    the leading summary position is in scope.
    """
    line = node.body[0].lineno - 1
    while line > node.lineno:
        if line in comments:
            return line
        if not source_lines[line - 1].strip():
            line -= 1
            continue
        return None
    return None


def check_summary_comment_as_docstring(path: Path, source: str) -> Iterator[Violation]:
    """A leading summary comment should be a docstring.

    A module, class, or function with no docstring whose first body
    position is a standalone prose comment carries a summary that ruff
    D401's mood check cannot see; move it into the docstring slot.
    """
    tree = _parse_python(path, source)
    if not isinstance(tree, ast.Module):
        return
    comments, _ = _comment_lines(source)
    source_lines = source.splitlines()
    yield from _module_summary_comment(tree, comments)
    for node in _summary_comment_owners(tree):
        if ast.get_docstring(node, clean=False) is not None or not node.body:
            continue
        line = _leading_comment_line(node, comments, source_lines)
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


def _module_summary_comment(
    tree: ast.Module, comments: dict[int, tuple[int, str]]
) -> Iterator[Violation]:
    """Flag a module whose first prose line is a comment, not a docstring.

    A leading shebang, coding, or tool-directive line is skipped, so the
    summary comment beneath it is still reached; the first non-directive
    standalone comment then decides, since only the leading position is
    in scope.
    """
    if ast.get_docstring(tree, clean=False) is not None:
        return
    first_code = tree.body[0].lineno if tree.body else None
    for line in sorted(comments):
        if first_code is not None and line >= first_code:
            return
        text = _comment_text(comments[line][1])
        if _is_directive_comment(text):
            continue
        if _is_prose_comment(text):
            yield Violation(
                line,
                comments[line][0] + 1,
                RS_SUMMARY_COMMENT_AS_DOCSTRING,
                "leading summary comment should be a module docstring",
            )
        return


def _dataclass_classes(tree: ast.Module) -> Iterator[ast.ClassDef]:
    """Yield every `@dataclass`-decorated class in `tree`."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and _has_dataclass_decorator(node):
            yield node


def _has_dataclass_decorator(node: ast.ClassDef) -> bool:
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Name) and target.id == "dataclass":
            return True
        if isinstance(target, ast.Attribute) and target.attr == "dataclass":
            return True
    return False


def _field_has_docstring(body: list[ast.stmt], index: int) -> bool:
    """Report whether the statement after a field is a string-literal docstring."""
    following = body[index + 1] if index + 1 < len(body) else None
    return (
        isinstance(following, ast.Expr)
        and isinstance(following.value, ast.Constant)
        and isinstance(following.value.value, str)
    )


def check_field_comment_as_docstring(path: Path, source: str) -> Iterator[Violation]:
    """A dataclass field comment should be a field docstring.

    A field documented with a trailing prose comment and no following
    string-literal field docstring should carry that text as the
    per-field docstring the house style prefers — the positive form of
    RS004's `Attributes:`-block ban.
    """
    tree = _parse_python(path, source)
    if not isinstance(tree, ast.Module):
        return
    _, trailing = _comment_lines(source)
    for node in _dataclass_classes(tree):
        for index, stmt in enumerate(node.body):
            if not isinstance(stmt, ast.AnnAssign):
                continue
            comment = trailing.get(stmt.end_lineno or stmt.lineno)
            if comment is None or not _is_prose_comment(_comment_text(comment)):
                continue
            if _field_has_docstring(node.body, index):
                continue
            yield Violation(
                stmt.lineno,
                stmt.col_offset + 1,
                RS_FIELD_COMMENT_AS_DOCSTRING,
                "document a dataclass field with a string-literal docstring "
                "below it, not a trailing comment",
            )


def check_filler_docstring_opening(path: Path, source: str) -> Iterator[Violation]:
    """A docstring may not open with a filler phrase.

    An opening like `This function`, `Helper to`, `Used to`, `Simply`,
    or `Just` restates the identifier or hedges rather than stating the
    contract; the summary's first words should name what the unit does.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in _walk_docstring_owners(tree):
        docstring = ast.get_docstring(node, clean=True)
        if docstring is None:
            continue
        summary = next(
            (line.strip() for line in docstring.splitlines() if line.strip()), ""
        )
        if _FILLER_OPENING_PATTERN.match(summary):
            yield Violation(
                getattr(node, "lineno", 1),
                getattr(node, "col_offset", 0) + 1,
                RS_FILLER_DOCSTRING_OPENING,
                "docstring opening restates the identifier; state the "
                "contract instead",
            )
