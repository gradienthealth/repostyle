"""Helpers shared across the package.

A helper used by a single module lives in that module; one used by two or more
-- the rule modules or the top-level runner -- lives here, so its callers stay
independent of each other.
"""

from __future__ import annotations

import ast
import re
import tomllib
from collections.abc import Iterator
from fnmatch import fnmatch
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

from repostyle._comments import extract_comments

# A pytest-collected test class: `Test` followed by an uppercase letter or the
# end of the name, so `Testimony` and `Tester` are not matched.
TEST_CLASS_PATTERN = re.compile(r"^Test([A-Z_]|$)")
TEST_FILE_PATTERN = re.compile(r"(^|/)(test_[^/]*|[^/]*_test)\.py$")

# A comment whose first token after the hash marks it as machinery, not prose.
# The shebang `#!` leads a module; the rest are tool directives that a prose
# check must skip.
_DIRECTIVE_COMMENT_PATTERN = re.compile(
    r"^[ \t]*(!|type:|style:|noqa|nosec|pragma|pylint:|mypy:|ruff:|isort:|fmt:"
    r"|codespell:)",
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

# A bulleted list item's marker: a dash, star, or plus then a space, opening a
# docstring or comment line's stripped text.
_BULLET_PATTERN = re.compile(r"^[-*+] ")
# A markdown table row (`|...|`) or a line made only of pipe, dash, plus, and
# equals characters (`+----+`, `====`, a `---` rule) opens content whose
# alignment is meaningful, so it is verbatim: never filled, never reflowed, and
# yielding no prose unit. Requiring the whole line to be those characters keeps
# flag-like prose (`--fix ...`) and bullets (`- `) from matching.
_VERBATIM_LINE_PATTERN = re.compile(r"^\||^[-+=][-+=|\s]*$")


def find_pyproject(start: Path) -> Path | None:
    """Walks up from `start` to find the nearest `pyproject.toml`."""
    start = start.resolve()
    return _find_pyproject_from(start if start.is_dir() else start.parent)


def _bool_config(table: dict[str, object], key: str) -> bool:
    """Reads a boolean flag from a repostyle config table under `key`.

    Returns `False` for a missing key or a non-boolean value, so an absent or
    malformed flag leaves the feature it gates switched off.
    """
    value = table.get(key)
    return value if isinstance(value, bool) else False


# An own-line comment as a `(lineno, column, string)` triple
_PositionedComment = tuple[int, int, str]


def _standalone_comment_blocks(
    path: Path, source: str
) -> Iterator[list[_PositionedComment]]:
    """Groups own-line comments into adjacent same-column blocks.

    A directive line, a trailing comment, a blank gap, or a column shift closes
    the open block, so each yielded block is one contiguous prose comment a
    reader sees as a paragraph.
    """
    block: list[_PositionedComment] = []
    previous: tuple[int, int] | None = None
    for comment in extract_comments(path, source):
        lineno, column, string = comment.lineno, comment.column, comment.string
        if comment.is_trailing or _is_directive_comment(_comment_text(string)):
            if block:
                yield block
            block, previous = [], None
            continue
        if previous is not None and previous != (lineno - 1, column):
            yield block
            block = []
        block.append((lineno, column, string))
        previous = (lineno, column)
    if block:
        yield block


def _comment_text(comment: str) -> str:
    """Returns a comment's prose, stripped of its leading hashes and space."""
    return comment.lstrip("#").strip()


def _dir_matches_config_glob(
    directory: Path, pyproject: Path | None, table: dict[str, object], key: str
) -> bool:
    """Reports whether a directory's whole subtree is excluded under `key`.

    Matches the directory's relative POSIX form with a trailing slash appended,
    so a file-oriented glob like `*venv/*` prunes the `venv` directory itself
    before its files are walked, not merely each file once read. Returns
    `False` when `key` configures no globs.
    """
    globs = _string_list(table, key)
    if not globs:
        return False
    relative = _relative_to_pyproject(directory, pyproject).rstrip("/") + "/"
    return any(fnmatch(relative, glob) for glob in globs)


def _gitignore_prunes_dir(
    directory: Path, pyproject: Path | None, rules: _GitignoreRules
) -> bool:
    """Reports whether a `.gitignore` pattern prunes a directory's subtree.

    Matches an anchored pattern against the directory's whole repo-relative
    path and a bare pattern against its own name, so a bare name prunes a
    directory so named at any depth. The directory is not pruned when a
    negation re-includes it or a descendant, or when an unanchored negation has
    switched pruning off for the repo. Returns `False` when no pattern is
    configured, so an absent or empty `.gitignore` prunes nothing.
    """
    if rules.is_disabled or not (rules.anchored or rules.bare):
        return False
    relative = _relative_to_pyproject(directory, pyproject)
    if any(_negation_covers(negated, relative) for negated in rules.negated_prefixes):
        return False
    if any(fnmatch(directory.name, pattern) for pattern in rules.bare):
        return True
    return any(fnmatch(relative, pattern) for pattern in rules.anchored)


def _negation_covers(negated: str, relative: str) -> bool:
    """Reports whether a negated path re-includes a directory or its subtree.

    A negated path guards the directory it names, an ancestor of it, and any
    descendant, so a `!keep/me` line stops the enclosing `keep` from being
    pruned out from under the re-included path.
    """
    return (
        negated == relative
        or negated.startswith(relative + "/")
        or relative.startswith(negated + "/")
    )


@lru_cache(maxsize=128)
def _parse_gitignore(gitignore: Path | None) -> _GitignoreRules:
    """Parses the directory-pruning patterns from a repo's `.gitignore`.

    Honors a deliberately small subset: a blank line and a `#` comment are
    skipped; a trailing-slash `foo/` and a bare `foo` both name a directory; a
    leading-slash `/foo` or an internal-slash `foo/bar` anchors to the repo
    root, while a bare name matches a directory so named at any depth. Glob
    matching is `fnmatch`, as the `exclude` globs already use, so a `*` may
    cross a path separator. A `!` negation is not honored as a re-inclusion: an
    anchored one only guards its own subtree from pruning, and an unanchored
    one -- whose any-depth reach cannot be bounded cheaply -- switches
    gitignore pruning off for the whole repo. Per-directory nested `.gitignore`
    files are not read. Returns empty rules when the file is absent or
    unreadable.
    """
    try:
        text = gitignore.read_text(encoding="utf-8") if gitignore else ""
    except (OSError, UnicodeDecodeError):
        text = ""
    buckets: dict[str, list[str]] = {"anchored": [], "bare": [], "negated": []}
    is_disabled = False
    for raw in text.splitlines():
        classified = _classify_gitignore_line(raw.rstrip())
        if classified is None:
            continue
        kind, body = classified
        if kind == "disable":
            is_disabled = True
        else:
            buckets[kind].append(body)
    return _GitignoreRules(
        tuple(buckets["anchored"]),
        tuple(buckets["bare"]),
        tuple(buckets["negated"]),
        is_disabled,
    )


def _classify_gitignore_line(line: str) -> tuple[str, str] | None:
    """Sorts a `.gitignore` line into a pruning-pattern kind and its body.

    Returns `None` for a blank line or a `#` comment. Otherwise returns the
    kind paired with the normalized directory body: `anchored` for a
    root-anchored or internal-slash pattern, `bare` for an any-depth name,
    `negated` for an anchored `!` re-inclusion whose subtree must be spared a
    prune, or `disable` for an unanchored `!` that switches pruning off.
    """
    if not line or line.startswith("#"):
        return None
    negation = line.startswith("!")
    body = line[1:] if negation else line
    if body.startswith("\\"):
        body = body[1:]
    body = body.strip("/")
    if not body:
        return None
    anchored = line.lstrip("!").startswith("/") or "/" in body
    if negation:
        return ("negated", body) if anchored else ("disable", body)
    return ("anchored" if anchored else "bare", body)


class _GitignoreRules(NamedTuple):
    """The `.gitignore` directory-pruning patterns repostyle honors.

    `anchored` patterns match a directory's whole repo-relative path; `bare`
    patterns match a directory's own name at any depth. `negated_prefixes`
    holds the anchored paths a `!` line re-includes, each guarding its subtree
    from a prune. `is_disabled` is set when an unanchored `!` line is present,
    whose any-depth reach cannot be reasoned about cheaply, so directory
    pruning is switched off for the whole repo rather than risk a mis-prune.
    """

    anchored: tuple[str, ...]
    bare: tuple[str, ...]
    negated_prefixes: tuple[str, ...]
    is_disabled: bool


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

    A prose unit -- one spanning lines, running multiple sentences, or standing
    as a docstring body paragraph -- must close with `.`, `!`, or `?`; returns
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


# The RS045 marker set: temporal and edit-narrative phrases that almost always
# narrate the change rather than the code, kept deliberately tight so the rule
# stays a floor under review rather than competing with it. The phrases are
# matched on a word boundary, case-insensitively, so an identifier fragment
# like `switched_to` (joined by an underscore) never matches.
_TEMPORAL_MARKER_PATTERN = re.compile(
    r"\b(previously|used to|formerly|originally|as discussed|we decided"
    r"|for now|changed to|switched to)\b",
    re.IGNORECASE,
)
# A backtick span quotes a phrase as a referenced token rather than narrating
# with it, so it is masked out before the marker match: a docstring that
# documents a marker as data (RS023's own card names `Used to`) is not itself
# flagged, and only a bare narrative use fires.
_BACKTICK_SPAN_PATTERN = re.compile(r"`[^`]*`")
# A URI, blanked beside the backtick spans so a token inside a `gs://` or
# `https://` path is not read as bare prose.
_PROSE_URI = re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]*://\S+")

# The house sentence dash, the one form prose sets a clause off with; RS054
# flags the forms below against it and rewrites them to it under `--fix`.
STANDARD_SENTENCE_DASH = " -- "

# The unambiguous sentence-dash glyphs, matched on masked prose text: an em
# dash matches spaced, glued, or half-spaced; an en dash matches spaced only,
# so an unspaced range (an `RSnnn` or numeric span) is left alone. Both are
# dashes whatever their neighbors, so their line-edge handling lives in the
# scanner, checked against the original text rather than via lookarounds -- a
# masked backtick span beside the dash must not hide it.
_UNAMBIGUOUS_DASH_PATTERNS = (
    re.compile(r" ?— ?"),
    re.compile(r" – "),  # noqa: RUF001
)
# The hyphen-built forms, bounded by letter lookarounds: a hyphen is also a
# minus, a bullet marker, and a flag prefix, so only a letter-flanked match
# reads as a sentence dash -- arithmetic (`n - 1`), a negative number, and a
# bullet marker never match. A doubled hyphen glued only on its right
# (`use --fix`) is exactly a CLI flag's shape, so of the mis-spaced doubled
# forms only the left-glued ones (`a--b`, `a-- b`), which no flag can be, are
# matched.
_HYPHEN_DASH_PATTERNS = (
    re.compile(r"(?<=[A-Za-z]) - (?=[A-Za-z])"),
    re.compile(r"(?<=[A-Za-z])(?:--|-- )(?=[A-Za-z])"),
)


def _nonstandard_dashes_in_prose(text: str) -> Iterator[tuple[int, str, str]]:
    """Yields each nonstandard sentence dash in a run of prose text.

    Reports a `(offset, found, replacement)` triple for every em dash, spaced
    en dash, letter-flanked spaced hyphen, or mis-spaced double hyphen doing
    sentence work in `text`, where `offset` is the match's 0-based position,
    `found` is the text as written, and `replacement` is always
    `STANDARD_SENTENCE_DASH`. Backtick code spans and URIs are blanked to
    equal-length whitespace first, so a dash in code font (`git log -- path`)
    or inside a URL is left alone and the offsets still index the original
    `text`; a dash beside such a span is still caught, since its line-edge test
    reads the original text. An em or en dash with nothing else on its line
    before or after it -- the wrap point of a reflowed paragraph -- is skipped,
    so a rewrite never leaves stray whitespace at a line edge. A replacement
    changes length, so a caller rewriting in place applies the triples in
    reverse offset order. Shared by RS054's docstring and comment checks.
    """
    masked = _blank_prose_spans(text)
    matches = [
        (match.start(), match.group())
        for pattern in _UNAMBIGUOUS_DASH_PATTERNS
        for match in pattern.finditer(masked)
        if text[: match.start()].strip() and text[match.end() :].strip()
    ]
    matches.extend(
        (match.start(), match.group())
        for pattern in _HYPHEN_DASH_PATTERNS
        for match in pattern.finditer(masked)
    )
    for offset, found in sorted(matches):
        yield offset, found, STANDARD_SENTENCE_DASH


def _blank_prose_spans(text: str) -> str:
    """Replaces each backtick span and URI in `text` with equal-length spaces.

    Keeping the run's length preserves every other character's offset, so a
    token position found in the blanked text indexes the original `text`.
    """
    without_spans = _BACKTICK_SPAN_PATTERN.sub(
        lambda match: " " * len(match.group()), text
    )
    return _PROSE_URI.sub(lambda match: " " * len(match.group()), without_spans)


def _temporal_markers(text: str) -> list[str]:
    """Lists the distinct RS045 markers a prose unit narrates with.

    Backtick spans are masked first, so a marker quoted as a referenced token
    does not count; only a bare narrative occurrence does. Each marker is
    lowercased and listed once, in first-mention order, so one prose unit
    yields at most one finding per distinct marker.
    """
    bare = _BACKTICK_SPAN_PATTERN.sub(" ", text)
    seen: list[str] = []
    for match in _TEMPORAL_MARKER_PATTERN.finditer(bare):
        marker = match.group(1).lower()
        if marker not in seen:
            seen.append(marker)
    return seen


# Cached because every rule scanning a file re-walks the same tree, and
# `ast.walk` costs two Python-level calls per node -- the largest single cost
# in a run before this. The key is the tree itself, an AST node hashing by
# identity, so an entry belongs to the exact tree `_parse_python` returned;
# holding that reference also pins it, leaving no way for a later tree to reuse
# a freed address and collide. Sized to match `_parse_python`, so a tree still
# held by the parse cache keeps its node list.
@lru_cache(maxsize=128)
def _walk_tree(tree: ast.AST) -> tuple[ast.AST, ...]:
    """Returns every node under `tree`, in `ast.walk` order.

    Callers share one tuple, so they read the nodes and never rewrite a tree.
    Pass a whole module tree: a subtree is walked once per file anyway, and
    caching one would evict the module lists that carry the win.
    """
    return tuple(ast.walk(tree))
