"""Helpers shared across rule modules.

A helper used by a single rule lives in that rule's module; one used by two or
more lives here so the rule modules stay independent of each other.
"""

from __future__ import annotations

import ast
import re
import tomllib
from fnmatch import fnmatch
from functools import lru_cache
from pathlib import Path

# A pytest-collected test class: `Test` followed by an uppercase letter or the
# end of the name, so `Testimony` and `Tester` are not matched.
TEST_CLASS_PATTERN = re.compile(r"^Test([A-Z_]|$)")
TEST_FILE_PATTERN = re.compile(r"(^|/)(test_[^/]*|[^/]*_test)\.py$")

# A comment whose first token after the hash marks it as machinery, not prose.
# The shebang `#!` leads a module; the rest are tool directives that a prose
# check must skip.
_DIRECTIVE_COMMENT_PATTERN = re.compile(
    r"^[ \t]*(!|type:|style:|noqa|pragma|pylint:|mypy:|ruff:|isort:|fmt:)",
)
# A PEP 263 encoding declaration, in either the plain `coding:` form or the
# Emacs `-*- coding: ... -*-` form, anywhere in the comment.
_CODING_DECLARATION_PATTERN = re.compile(r"coding[:=]\s*[-\w.]+")

# Closing characters that may sit after a sentence's terminal mark, so a unit
# ending `note.)` or `said "go."` still reads as terminated.
_TRAILING_CLOSERS = ')"'
# A sentence break: a terminal mark, any closing quotes or brackets,
# whitespace, then a capital. The token ending in the mark decides whether the
# break is real; an initialism, a numbered ordinal, or a known abbreviation
# carries an internal period without ending a sentence.
_SENTENCE_BOUNDARY_PATTERN = re.compile(r"[.!?][)\"']*\s+[A-Z]")
_INITIALISM_PATTERN = re.compile(r"(?:[A-Za-z]\.)+|\d+\.")
_SENTENCE_ABBREVIATIONS = frozenset(
    {"etc.", "vs.", "cf.", "al.", "Dr.", "Mr.", "Mrs.", "Ms.", "St.", "Inc.", "Ltd."}
)


def find_pyproject(start: Path) -> Path | None:
    """Walks up from `start` to find the nearest `pyproject.toml`."""
    start = start.resolve()
    return _find_pyproject_from(start if start.is_dir() else start.parent)


def _comment_text(comment: str) -> str:
    """Returns a comment's prose, stripped of its leading hashes and space."""
    return comment.lstrip("#").strip()


@lru_cache(maxsize=128)
def _find_pyproject_from(directory: Path) -> Path | None:
    """Walks up from `directory` to the nearest `pyproject.toml`.

    Caches on the directory rather than the file so a directory scan walks up
    once for all its files, not once per file across path expansion and every
    rule.
    """
    for candidate in (directory, *directory.parents):
        pyproject = candidate / "pyproject.toml"
        if pyproject.is_file():
            return pyproject
    return None


def _has_decorator(
    node: ast.FunctionDef | ast.AsyncFunctionDef, names: frozenset[str] | set[str]
) -> bool:
    """Reports whether the definition carries a decorator named in `names`.

    Match both the bare (`@override`) and dotted (`@typing.override`) forms,
    comparing only the final attribute name, and see through a decorator call
    (`@cache()`) to the name it applies.
    """
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Name) and target.id in names:
            return True
        if isinstance(target, ast.Attribute) and target.attr in names:
            return True
    return False


def _has_sentence_boundary(text: str) -> bool:
    """Reports whether `text` runs more than one sentence.

    A terminal mark followed by whitespace and a capital opens a second
    sentence, unless the token ending in the mark is an initialism, a decimal,
    or a known abbreviation, which carry an internal period without closing a
    sentence.
    """
    for match in _SENTENCE_BOUNDARY_PATTERN.finditer(text):
        token = text[: match.start() + 1].split()[-1]
        if token.lower() in _SENTENCE_ABBREVIATIONS:
            continue
        if _INITIALISM_PATTERN.fullmatch(token):
            continue
        return True
    return False


def _is_prose_comment(text: str) -> bool:
    """Reports whether a comment's text reads as a documenting sentence.

    Prose is capitalised and at least three words. A tool directive, a shebang,
    a coding line, and a commented-out statement are all excluded, so the check
    fires only on a sentence a docstring should carry.
    """
    if _is_directive_comment(text):
        return False
    if not text[:1].isupper() or len(text.split()) < 3:
        return False
    return not _is_code_fragment(text)


def _is_code_fragment(text: str) -> bool:
    """Reports whether a comment's text parses as commented-out Python.

    A fragment that parses to anything other than a bare name, attribute,
    comparison, or boolean expression is code: an assignment, import, call, or
    keyword statement. Those four expression shapes are the ones an English
    sentence parses into, so prose phrased around `is`, `in`, `and`, or `or`
    (`Cache is empty`) is not mistaken for code. The boundary is conservative:
    text that does not parse is prose, and a sentence parsing to another shape
    falls to code, so the rule under-fires rather than over-fires.
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


def _is_directive_comment(text: str) -> bool:
    """Reports whether a comment's text is a tool directive or coding line."""
    return bool(
        _DIRECTIVE_COMMENT_PATTERN.match(text)
        or _CODING_DECLARATION_PATTERN.search(text)
    )


def _is_test_file(path: Path) -> bool:
    """Reports whether a path is a test module by location or filename."""
    posix = _posix(path)
    return "tests/" in posix or TEST_FILE_PATTERN.search(posix) is not None


def _join_source_lines(source: str, lines: list[str]) -> str:
    """Rejoins edited `lines`, keeping the line endings of `source`.

    The source's newline style and its final-newline presence are carried over,
    so a fixer that splits with `splitlines` and rewrites a few lines does not
    churn the file's endings.
    """
    newline = "\r\n" if "\r\n" in source else "\n"
    rejoined = newline.join(lines)
    return rejoined + newline if source.endswith("\n") else rejoined


def _matches_config_glob(
    path: Path, pyproject: Path | None, table: dict[str, object], key: str
) -> bool:
    """Reports whether `path` matches any glob configured under `key`.

    Matches `path`, resolved to its POSIX form relative to `pyproject`, against
    each glob configured under `key`. Returns `False` when `key` configures no
    globs, so an absent key never excludes anything.
    """
    globs = _string_list(table, key)
    if not globs:
        return False
    relative = _relative_to_pyproject(path, pyproject)
    return any(fnmatch(relative, glob) for glob in globs)


# Cache on (path, source) so each file is parsed once and its tree shared
# across rules.
@lru_cache(maxsize=128)
def _parse_python(path: Path, source: str) -> ast.AST | None:
    if path.suffix != ".py":
        return None
    try:
        return ast.parse(source)
    except SyntaxError:
        return None


def _relative_to_pyproject(path: Path, pyproject: Path | None) -> str:
    """Returns `path` as a POSIX path relative to the pyproject's directory.

    Falls back to the path as written when there is no pyproject or `path` lies
    outside its directory, so the result is always a usable relative string.
    """
    if pyproject is None:
        return _posix(path)
    try:
        return _posix(path.resolve().relative_to(pyproject.parent))
    except ValueError:
        return _posix(path)


def _posix(path: Path) -> str:
    return str(path).replace("\\", "/")


@lru_cache(maxsize=128)
def _repostyle_table(pyproject: Path | None) -> dict[str, object]:
    """Reads the `[tool.repostyle]` table from a pyproject file, if any."""
    if pyproject is None:
        return {}
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return data.get("tool", {}).get("repostyle", {})


def _string_list(table: dict[str, object], key: str) -> tuple[str, ...]:
    """Reads a list of strings from a repostyle config table under `key`."""
    configured = table.get(key, ())
    if isinstance(configured, str):
        configured = (configured,)
    if not isinstance(configured, list | tuple):
        return ()
    return tuple(str(item) for item in configured if str(item))


def _terminal_punctuation_fault(text: str, *, is_prose: bool) -> str | None:
    """Classifies a prose unit's terminal punctuation against the house rule.

    A prose unit — one spanning lines, running multiple sentences, or standing
    as a docstring body paragraph — must close with `.`, `!`, or `?`; returns
    `"missing"` when it does not. A single-line single-sentence fragment is a
    label and must not close with a period; returns `"extra"` when it does. A
    unit ending with a colon introduces a list, and one ending in a URL cannot
    take punctuation, so both are exempt. Returns `None` when the unit
    conforms.
    """
    stripped = _strip_trailing_closers(text)
    if not stripped or stripped.endswith(":"):
        return None
    if "://" in stripped.rsplit(maxsplit=1)[-1]:
        return None
    if is_prose:
        return None if stripped[-1] in ".!?" else "missing"
    return "extra" if stripped[-1] == "." else None


def _strip_trailing_closers(text: str) -> str:
    """Returns `text` without trailing whitespace or sentence-closing marks."""
    return text.rstrip().rstrip(_TRAILING_CLOSERS)
