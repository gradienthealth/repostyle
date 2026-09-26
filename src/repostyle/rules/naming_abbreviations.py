"""Focused helpers extracted from a larger module."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

from repostyle._shared import (
    _blank_prose_spans,
    _parse_python,
    _walk_tree,
)
from repostyle.rules._violation import (
    RS_BANNED_ABBREVIATION,
    Violation,
)
from repostyle.rules.naming_special import (
    DISCOURAGED_CLASS_SUFFIXES as DISCOURAGED_CLASS_SUFFIXES,
)
from repostyle.rules.naming_special import (
    DISFAVORED_GCP_TERMS as DISFAVORED_GCP_TERMS,
)
from repostyle.rules.naming_special import (
    GCP_COLLECTION_NOUNS as GCP_COLLECTION_NOUNS,
)
from repostyle.rules.naming_special import (
    check_discouraged_class_suffix as check_discouraged_class_suffix,
)
from repostyle.rules.naming_special import (
    check_exception_alias as check_exception_alias,
)
from repostyle.rules.naming_special import (
    check_gcp_bare_identifier as check_gcp_bare_identifier,
)
from repostyle.rules.naming_special import (
    check_no_make_in_production as check_no_make_in_production,
)
from repostyle.rules.naming_special import (
    disfavored_gcp_terms_in_prose as disfavored_gcp_terms_in_prose,
)

CAPWORDS_WORD_PATTERN = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+")

_PROSE_ACRONYM_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_.-])[A-Za-z][A-Za-z0-9]*(?![A-Za-z0-9_-])(?!\.[A-Za-z0-9])"
)

BANNED_ABBREVIATIONS: frozenset[str] = frozenset(
    {
        "btn",
        "cfg",
        "conn",
        "ctx",
        "idx",
        "mgr",
        "mngr",
        "req",
        "res",
        "resp",
        "usr",
    }
)


def check_banned_abbreviation(path: Path, source: str) -> Iterator[Violation]:
    """Flags an introduced name that drops letters from a known word.

    Scope: class, function, and parameter names, an `as` alias on an import,
    and any assignment, loop, with-as, comprehension, or walrus target. The
    name is split into its snake_case and CapWords words, and a word equal to a
    banned abbreviation (`cfg`, `ctx`, `req`, `resp`, `conn`, ...) is rejected
    in favor of the spelled-out word. Attribute names and string contents are
    not checked, so a literal `"cfg"` and a third-party `response.idx` access
    are both left alone. An import without an alias is left alone too, since
    the imported name is the source module's to spell, not this file's.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in _walk_tree(tree):
        for name, lineno, col_offset in _abbreviation_named_targets(node):
            yield from _abbreviation_violations(name, lineno, col_offset)


def miscased_acronyms_in_prose(
    text: str, canonical_casing: dict[str, str]
) -> Iterator[tuple[int, str, str]]:
    """Yields each miscased acronym occurrence in a run of prose text.

    Reports a `(offset, found, canonical)` triple for every whole-word token in
    `text` that case-insensitively matches an acronym in `canonical_casing` but
    is not already in its canonical casing, where `offset` is the token's
    0-based position in `text`, `found` is the token as written, and
    `canonical` is the casing to rewrite it to. Backtick code spans and URIs
    are blanked to equal-length whitespace first, so a token in code font or
    inside a URL is left alone and the reported offsets still index the
    original `text`. Because a case-only rewrite never changes length, the
    offset and `found` locate an in-place replacement exactly. Shared by
    RS049's docstring and comment checks, which supply the prose region and
    resolve `canonical_casing` from config.
    """
    masked = _blank_prose_spans(text)
    for match in _PROSE_ACRONYM_TOKEN.finditer(masked):
        token = match.group()
        canonical = canonical_casing.get(token.upper())
        if canonical is not None and token != canonical:
            yield match.start(), token, canonical


def _abbreviation_named_targets(node: ast.AST) -> Iterator[tuple[str, int, int]]:
    """Yields the at-most-one abbreviation-checked name a node introduces.

    Resolves a class, function, or parameter name, an aliased import, or a
    store-context `Name` target to its `(name, lineno, col_offset)` triple;
    yields nothing for any other node.
    """
    if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
        yield (node.name, node.lineno, node.col_offset)
    elif isinstance(node, ast.arg):
        yield (node.arg, node.lineno, node.col_offset)
    elif isinstance(node, ast.alias) and node.asname is not None:
        yield (node.asname, node.lineno, node.col_offset)
    elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
        yield (node.id, node.lineno, node.col_offset)


def _abbreviation_violations(
    name: str, lineno: int, col_offset: int
) -> Iterator[Violation]:
    """Yields a violation for each banned abbreviation among a name's words."""
    for word in identifier_words(name):
        if word in BANNED_ABBREVIATIONS:
            yield Violation(
                lineno,
                col_offset + 1,
                RS_BANNED_ABBREVIATION,
                f"'{name}' uses the abbreviation '{word}'; spell the word out",
            )


def identifier_words(name: str) -> Iterator[str]:
    """Yields the lowercased words composing a snake_case or CapWords name."""
    for part in name.split("_"):
        for word in CAPWORDS_WORD_PATTERN.findall(part):
            yield word.lower()
