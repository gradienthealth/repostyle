"""Helpers shared across rule modules.

A helper used by a single rule lives in that rule's module; one used by
two or more lives here so the rule modules stay independent of each
other.
"""

from __future__ import annotations

import ast
import re
from functools import lru_cache
from pathlib import Path

# A pytest-collected test class: `Test` followed by an uppercase letter
# or the end of the name, so `Testimony` and `Tester` are not matched.
TEST_CLASS_PATTERN = re.compile(r"^Test([A-Z_]|$)")
TEST_FILE_PATTERN = re.compile(r"(^|/)(test_[^/]*|[^/]*_test)\.py$")

# A comment whose first token after the hash marks it as machinery, not
# prose. The shebang `#!` leads a module; the rest are tool directives
# that a prose check must skip.
_DIRECTIVE_COMMENT_PATTERN = re.compile(
    r"^[ \t]*(!|type:|style:|noqa|pragma|pylint:|mypy:|ruff:|isort:|fmt:)",
)
# A PEP 263 encoding declaration, in either the plain `coding:` form or
# the Emacs `-*- coding: ... -*-` form, anywhere in the comment.
_CODING_DECLARATION_PATTERN = re.compile(r"coding[:=]\s*[-\w.]+")

# Closing characters that may sit after a sentence's terminal mark, so a
# unit ending `note.)` or `said "go."` still reads as terminated.
_TRAILING_CLOSERS = ')"'
# A sentence break: a terminal mark, any closing quotes or brackets,
# whitespace, then a capital. The token ending in the mark decides
# whether the break is real; an initialism, a numbered ordinal, or a
# known abbreviation carries an internal period without ending a
# sentence.
_SENTENCE_BOUNDARY_PATTERN = re.compile(r"[.!?][)\"']*\s+[A-Z]")
_INITIALISM_PATTERN = re.compile(r"(?:[A-Za-z]\.)+|\d+\.")
_SENTENCE_ABBREVIATIONS = frozenset(
    {"etc.", "vs.", "cf.", "al.", "Dr.", "Mr.", "Mrs.", "Ms.", "St.", "Inc.", "Ltd."}
)


def _has_decorator(
    node: ast.FunctionDef | ast.AsyncFunctionDef, names: frozenset[str] | set[str]
) -> bool:
    """Report whether the definition carries a decorator named in `names`.

    Match both the bare (`@override`) and dotted (`@typing.override`)
    forms, comparing only the final attribute name, and see through a
    decorator call (`@cache()`) to the name it applies.
    """
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Name) and target.id in names:
            return True
        if isinstance(target, ast.Attribute) and target.attr in names:
            return True
    return False


def _is_test_file(path: Path) -> bool:
    """Report whether a path is a test module by location or filename."""
    posix = _posix(path)
    return "tests/" in posix or TEST_FILE_PATTERN.search(posix) is not None


def _posix(path: Path) -> str:
    return str(path).replace("\\", "/")


def find_pyproject(start: Path) -> Path | None:
    """Walk up from `start` to find the nearest `pyproject.toml`."""
    start = start.resolve()
    directory = start if start.is_dir() else start.parent
    for candidate in (directory, *directory.parents):
        pyproject = candidate / "pyproject.toml"
        if pyproject.is_file():
            return pyproject
    return None


# Cache on (path, source) so each file is parsed once and its tree
# shared across rules.
@lru_cache(maxsize=128)
def _parse_python(path: Path, source: str) -> ast.AST | None:
    if path.suffix != ".py":
        return None
    try:
        return ast.parse(source)
    except SyntaxError:
        return None


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

    A fragment that parses to anything other than a bare name,
    attribute, comparison, or boolean expression is code: an assignment,
    import, call, or keyword statement. Those four expression shapes are
    the ones an English sentence parses into, so prose phrased around
    `is`, `in`, `and`, or `or` (`Cache is empty`) is not mistaken for
    code. The boundary is conservative: text that does not parse is
    prose, and a sentence parsing to another shape falls to code, so the
    rule under-fires rather than over-fires.
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


def _strip_trailing_closers(text: str) -> str:
    """Return `text` without trailing whitespace or sentence-closing marks."""
    return text.rstrip().rstrip(_TRAILING_CLOSERS)


def _has_sentence_boundary(text: str) -> bool:
    """Report whether `text` runs more than one sentence.

    A terminal mark followed by whitespace and a capital opens a second
    sentence, unless the token ending in the mark is an initialism, a
    decimal, or a known abbreviation, which carry an internal period
    without closing a sentence.
    """
    for match in _SENTENCE_BOUNDARY_PATTERN.finditer(text):
        token = text[: match.start() + 1].split()[-1]
        if token.lower() in _SENTENCE_ABBREVIATIONS:
            continue
        if _INITIALISM_PATTERN.fullmatch(token):
            continue
        return True
    return False


def _terminal_punctuation_fault(text: str, *, is_prose: bool) -> str | None:
    """Classify a prose unit's terminal punctuation against the house rule.

    A prose unit — one spanning lines, running multiple sentences, or
    standing as a docstring body paragraph — must close with `.`, `!`,
    or `?`; return `"missing"` when it does not. A single-line single-
    sentence fragment is a label and must not close with a period;
    return `"extra"` when it does. A unit ending with a colon introduces
    a list, and one ending in a URL cannot take punctuation, so both are
    exempt. Return `None` when the unit conforms.
    """
    stripped = _strip_trailing_closers(text)
    if not stripped or stripped.endswith(":"):
        return None
    if "://" in stripped.rsplit(maxsplit=1)[-1]:
        return None
    if is_prose:
        return None if stripped[-1] in ".!?" else "missing"
    return "extra" if stripped[-1] == "." else None
