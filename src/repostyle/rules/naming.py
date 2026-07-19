"""Identifier rules.

Acronym casing, banned abbreviations, vague class suffixes, boolean naming, the
`make_`-in-production ban, and exception-alias naming.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from repostyle._shared import (
    _BACKTICK_SPAN_PATTERN,
    TEST_CLASS_PATTERN,
    _has_decorator,
    _is_test_file,
    _parse_python,
    _repostyle_table,
    _string_list,
    find_pyproject,
)
from repostyle.rules._violation import (
    RS_ACRONYM_CASING,
    RS_BANNED_ABBREVIATION,
    RS_BOOLEAN_PREFIX_REQUIRED,
    RS_DISCOURAGED_CLASS_SUFFIX,
    RS_EXCEPTION_ALIAS,
    RS_GCP_BARE_IDENTIFIER,
    RS_NO_MAKE_IN_PRODUCTION,
    RS_NO_NEGATED_BOOLEAN,
    RS_PREDICATE_FUNCTION_NAMING,
    Violation,
)

# Each entry carries its own canonical casing, which is not always `.upper()`:
# a mixed-case acronym like `IPv6` reads correctly only one way, while `NAT`
# and the rest are all-uppercase. RS001 (identifiers) matches on the uppercased
# form below; RS049 (prose) rewrites a miscased occurrence to the casing here.
ACRONYMS: tuple[str, ...] = (
    "API",
    "DOB",
    "FHIR",
    "GCP",
    "HTTP",
    "ID",
    "IPv6",
    "JSON",
    "JWT",
    "MRN",
    "NAT",
    "SMART",
    "URL",
)

_CAPWORDS_WORD = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+")
# Each acronym's uppercased form keyed to its canonical casing. The uppercase
# key drives RS001's case-insensitive membership test against the letter-only
# CapWords words above; a digit-bearing key like `IPV6` can never equal one of
# those words, so `IPv6` is inert for RS001 while still carrying the target
# casing RS049 rewrites prose to.
_CANONICAL_ACRONYMS: dict[str, str] = {word.upper(): word for word in ACRONYMS}
_ACRONYM_SET = frozenset(_CANONICAL_ACRONYMS)

# Acronyms whose lowercased form is a common English word or an everyday
# shorthand, so RS049 leaves them in prose to avoid rewriting the word: `SMART`
# lowercases to the adjective `smart`, and `id` reads as the ordinary shorthand
# for `identifier`. RS001 keeps them, since a CapWords identifier is
# unambiguously code where prose is not; a repo that wants one enforced in its
# prose reintroduces it through `acronyms-extra`, which overrides this set.
_PROSE_AMBIGUOUS_ACRONYMS: frozenset[str] = frozenset({"ID", "SMART"})

# Acronyms a prose *term-map* rule owns instead, so RS049 leaves them alone in
# prose and the two rules never fight over the same token. RS050 rewrites `GCP`
# in prose to `Google Cloud` (the current umbrella brand), a substitution, not
# a recasing, so RS049 must not first recase `gcp` to `GCP`. RS001 keeps `GCP`,
# since a CapWords identifier's casing is still correct; only the prose set
# drops it, and `acronyms-extra` cannot reintroduce it, since RS050 owns it.
_PROSE_TERM_OWNED_ACRONYMS: frozenset[str] = frozenset({"GCP"})

# A whole-word prose token RS049 tests against the acronym set. The lookarounds
# reject a hyphen glued to a letter or digit on either side too, so a
# hyphenated compound such as `fhir-ingestor` (a proper name whose lowercase is
# correct) is one token that never matches, while a standalone `ipv6` or `Nat`
# still does. A digit is allowed after the leading letter so `ipv6` reads as
# one token rather than `ipv` plus a stray `6`.
_PROSE_ACRONYM_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_-])[A-Za-z][A-Za-z0-9]*(?![A-Za-z0-9_-])"
)
# A URI, blanked before the token scan so an acronym inside a `gs://` or
# `https://` path is not read as a bare prose reference to correct.
_PROSE_URI = re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]*://\S+")

# RS050's curated map of a disfavored Google Cloud product or brand name in
# prose to its preferred current form. Only unambiguous substitutions live
# here: `GCS` and `GCP` are Google's own retired shorthands, and `Big Query`,
# `BigTable`, and `PubSub` are miswritten product names whose canonical
# spelling is fixed. A bare `Storage`, `Monitoring`, or `Logging` is too often
# an ordinary English word to rewrite mechanically, so the convention doc and
# the review lens own those. Keys are matched case- and
# whitespace-insensitively; the value is written verbatim.
DISFAVORED_GCP_TERMS: dict[str, str] = {
    "Google Cloud Platform": "Google Cloud",
    "GCP": "Google Cloud",
    "GCS": "Cloud Storage",
    "GCE": "Compute Engine",
    "Big Query": "BigQuery",
    "BigTable": "Bigtable",
    "Big Table": "Bigtable",
    "PubSub": "Pub/Sub",
    "Pub Sub": "Pub/Sub",
}

# Each disfavored term keyed by its normalized form — internal whitespace
# collapsed to one space, uppercased — so a case- and spacing-insensitive match
# resolves back to its preferred replacement.
_GCP_TERM_REPLACEMENT: dict[str, str] = {
    re.sub(r"\s+", " ", term).upper(): preferred
    for term, preferred in DISFAVORED_GCP_TERMS.items()
}

# A whole-word alternation of the disfavored terms, longest first so a phrase
# (`Google Cloud Platform`) wins over a shorter key at the same position. Each
# term's internal spaces match one or more whitespace characters; the
# lookarounds reject a letter, digit, or hyphen glued on either end, so a
# substring (`GCS` in `GCSError`, `gce` in `gce-node`) never matches. The scan
# is case-insensitive, since a lowercased `gcp` is the same disfavored word.
_GCP_TERM_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_-])(?:"
    + "|".join(
        r"\s+".join(re.escape(word) for word in term.split())
        for term in sorted(DISFAVORED_GCP_TERMS, key=len, reverse=True)
    )
    + r")(?![A-Za-z0-9_-])",
    re.IGNORECASE,
)

_TYPE_FACTORY_NAMES = frozenset({"TypeVar", "NewType", "ParamSpec", "TypeVarTuple"})

# PEP 695 type-alias / type-parameter syntax parses only on Python 3.12+, so
# these AST node classes are absent on 3.11. Resolve them defensively to an
# empty tuple there: `isinstance(node, ())` is always False, and no PEP 695
# node can appear in a 3.11 parse anyway.
_PEP695_TYPE_ALIAS = getattr(ast, "TypeAlias", ())
_PEP695_TYPE_PARAMS = tuple(
    node
    for node in (
        getattr(ast, "TypeVar", None),
        getattr(ast, "ParamSpec", None),
        getattr(ast, "TypeVarTuple", None),
    )
    if node is not None
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

# Google Cloud resource collection nouns whose bare, string-typed parameter
# almost always carries the resource's bare id (AIP-122), so RS051 asks for the
# `_id` suffix. Kept tight to hold the false-positive rate down: each reads
# unambiguously as a Google Cloud resource id when a `str` parameter is named
# for it, where a wider set (`table`, `key`, `service`, `zone`) would collide
# with ordinary non-cloud uses. The deeper name/path/handle distinction stays
# with the review lens, per `docs/gcp-naming.md`.
GCP_COLLECTION_NOUNS: frozenset[str] = frozenset(
    {"project", "bucket", "dataset", "topic", "subscription", "instance"}
)

DISCOURAGED_CLASS_SUFFIXES: tuple[str, ...] = ("Helper", "Manager", "Util", "Utils")

BOOLEAN_PREFIXES: frozenset[str] = frozenset({"can", "has", "is", "should"})

# RS044's accepted openings: RS026's boolean prefixes, plus `needs`/`allows`,
# which read as a yes/no question on a function (`needs_refresh`, `allows_x`)
# though they are not among the noun/attribute prefixes RS026 checks.
PREDICATE_PREFIXES: frozenset[str] = BOOLEAN_PREFIXES | frozenset({"allows", "needs"})

# Decorators that leave a boolean function's name outside the author's control,
# so RS044 leaves the name alone: an `@override`/`@overload` implements a name
# a supertype or stub already fixed.
_PREDICATE_ESCAPE_DECORATORS: frozenset[str] = frozenset({"override", "overload"})

NEGATION_WORDS: frozenset[str] = frozenset({"no", "not"})

# `exc` optionally followed by digits: the blessed `exc`, plus `exc2`, `exc3`
# for a nested handler that must not shadow an outer alias. `exc` is the one
# abbreviation exempt from RS010, since it is the universal Python idiom for
# the exception in hand.
_BLESSED_EXCEPTION_ALIAS = re.compile(r"exc\d*")

_MIN_DESCRIPTIVE_ALIAS_LENGTH = 4


def check_acronym_casing(path: Path, source: str) -> Iterator[Violation]:
    """Flags CapWords identifiers where a known acronym is not all uppercase.

    Scope: class names, PEP 695 `type` aliases, PEP 695 type parameters
    (`class C[T]`, `def f[T]`), and `TypeVar`/`NewType`/`ParamSpec`/
    `TypeVarTuple` factory calls in either `Name` or `typing.TypeVar` attribute
    form. A repo extends the acronym set for its own domain via
    `acronyms-extra` and drops one via `acronyms-exclude` in
    `[tool.repostyle]`.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    acronyms = _effective_acronyms(find_pyproject(path))
    for node in ast.walk(tree):
        for name, lineno, col_offset in _acronym_named_targets(node):
            yield from _acronym_violations(name, lineno, col_offset, acronyms)


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
    for node in ast.walk(tree):
        for name, lineno, col_offset in _abbreviation_named_targets(node):
            yield from _abbreviation_violations(name, lineno, col_offset)


def check_discouraged_class_suffix(path: Path, source: str) -> Iterator[Violation]:
    """Flags a class name ending in a vague agent suffix.

    `Manager`, `Helper`, `Util`, and `Utils` name what a class loosely does
    rather than what it is, and tend to accrete unrelated procedures; name the
    responsibility instead (`ConnectionPool`, not `ConnectionManager`). A
    pytest-style test class (`Test` followed by a capitalized word, as in
    `TestContextManager`) is exempt, since it is named for the unit under test.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or TEST_CLASS_PATTERN.match(node.name):
            continue
        for suffix in DISCOURAGED_CLASS_SUFFIXES:
            if node.name.endswith(suffix):
                yield Violation(
                    node.lineno,
                    node.col_offset + 1,
                    RS_DISCOURAGED_CLASS_SUFFIX,
                    f"class '{node.name}' ends in '{suffix}'; name the "
                    f"responsibility, not a vague agent role",
                )
                break


def check_no_negated_boolean(path: Path, source: str) -> Iterator[Violation]:
    """Flags a boolean name that embeds its own negation.

    A name opening with a boolean prefix (`is`, `has`, `can`, `should`) and
    carrying `not` or `no` as a later word reads as a standing negative —
    `is_not_stale`, `has_no_results` — so every call site must double-negate it
    (`if not is_not_stale`). Name the positive (`is_fresh`, `has_results`) and
    negate where the value is read.
    Scope: function and method names, parameters, and names bound by assignment
    or annotation. The negation is matched only as a whole snake_case or
    CapWords word, so `is_notable` and `is_north` (where `not` or `no` is
    merely a leading substring) are left alone.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in ast.walk(tree):
        for name, lineno, col_offset in _negated_boolean_named_targets(node):
            yield from _negated_boolean_violations(name, lineno, col_offset)


def check_boolean_prefix_required(path: Path, source: str) -> Iterator[Violation]:
    """Flags a boolean name that does not read as a yes/no question.

    A boolean should answer a yes/no question, so it opens with `is`, `has`,
    `can`, or `should` (`is_finalized`, `has_results`); a bare `valid` or
    `enabled` does not. Scope: `bool`-annotated parameters and `bool`-annotated
    variable and attribute targets. Detection is by annotation, so an
    unannotated local is left alone and the signal stays free of guesses; a
    `-> bool` function is left alone too, since a predicate verb (`startswith`,
    `suppresses`) is the idiomatic name for one. Advisory: it marks names to
    reconsider rather than failing the run.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in ast.walk(tree):
        for name, lineno, col_offset in _boolean_prefix_named_targets(node):
            yield from _boolean_prefix_violations(name, lineno, col_offset)


def check_predicate_function_naming(path: Path, source: str) -> Iterator[Violation]:
    """Flags a `-> bool` function named as a bare state word, not a question.

    A boolean function should read as the yes/no question its call site asks,
    so a single-word name that is a bare adjective or state noun (`valid`,
    `ready`, `enabled`) is flagged in favor of a predicate-prefixed form
    (`is_valid`). The check stays narrow to keep its false-positive rate near
    zero: it fires only on a single bare word, since a multi-word name already
    carries a predicate somewhere (`field_has_docstring`,
    `branch_asserts_directly`), and it accepts a third-person verb (a word
    ending in `s`, like `matches` or `suppresses`), the idiomatic
    predicate-verb name a boolean function may take. A dunder, a property
    setter, and an `@override`/`@overload` are exempt, since their names are
    fixed elsewhere. Detection is by the bare `bool` return annotation, so an
    unannotated or union-returning function is left alone.
    Advisory: it marks a name to reconsider rather than failing the run.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            yield from _predicate_naming_violation(node)


def _predicate_naming_violation(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> Iterator[Violation]:
    """Yields a boolean function's predicate-naming violation, if any."""
    if not _is_bool_annotation(node.returns):
        return
    if (
        _is_dunder(node.name)
        or _is_property_setter(node)
        or _has_decorator(node, _PREDICATE_ESCAPE_DECORATORS)
    ):
        return
    word = node.name.lstrip("_")
    if "_" in word or not word:
        return
    if word in PREDICATE_PREFIXES or word.lower().endswith("s"):
        return
    yield Violation(
        node.lineno,
        node.col_offset + 1,
        RS_PREDICATE_FUNCTION_NAMING,
        f"boolean function '{node.name}' reads as a state, not a yes/no "
        f"question; prefix it with is, has, can, or should (e.g. 'is_{word}')",
    )


def check_exception_alias(path: Path, source: str) -> Iterator[Violation]:
    """Flags a non-descriptive `except ... as` alias.

    A caught exception's bound name must be `exc`, `exc` followed by digits
    (`exc2`) for a nested handler, or a descriptive name of at least four
    characters (`validation_error`, `original_exc`); the noise aliases `e`,
    `ex`, and `err` are rejected. A bare `except X:` binding no name is left
    alone.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.ExceptHandler) or node.name is None:
            continue
        name = node.name
        if (
            _BLESSED_EXCEPTION_ALIAS.fullmatch(name)
            or len(name) >= _MIN_DESCRIPTIVE_ALIAS_LENGTH
        ):
            continue
        yield Violation(
            node.lineno,
            node.col_offset + 1,
            RS_EXCEPTION_ALIAS,
            f"exception alias '{name}' is non-descriptive; use 'exc', "
            f"'exc2' for a nested handler, or a descriptive name",
        )


def check_no_make_in_production(path: Path, source: str) -> Iterator[Violation]:
    """Flags a `make_` function defined outside a test module.

    `make_` is reserved for test fixtures (`make_bundle`, `make_patient`). In
    production it hides whether the call assembles in memory or changes the
    world; use `build_` for pure in-memory assembly or `create_` for
    construction with a side effect. A function under a `tests/` path, a
    `test_*` / `*_test` module, or a `conftest.py` is a fixture and left alone.
    The `make_` prefix must be a whole word, so `makedirs` and a bare `make` (a
    builder's terminal method) are not flagged.
    """
    if _is_test_file(path) or path.name == "conftest.py":
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in ast.walk(tree):
        if isinstance(
            node, ast.FunctionDef | ast.AsyncFunctionDef
        ) and node.name.startswith("make_"):
            yield Violation(
                node.lineno,
                node.col_offset + 1,
                RS_NO_MAKE_IN_PRODUCTION,
                f"'{node.name}' uses the fixture-only verb 'make_' in "
                f"production; use 'build_' (in-memory) or 'create_' "
                f"(side-effecting)",
            )


def check_gcp_bare_identifier(path: Path, source: str) -> Iterator[Violation]:
    """Flags a string parameter named for a Google Cloud resource collection.

    A `str`-typed parameter named exactly for a Google Cloud resource
    collection (`project`, `bucket`, `dataset`, `topic`, `subscription`,
    `instance`) almost always holds that resource's bare id, which AIP-122
    distinguishes from the qualified resource name (the `{collection}/{id}`
    path). The `_id` suffix (`project` to `project_id`) states which of the two
    the value carries, so a caller reads the intent without tracing the
    dataflow. Only a string-typed parameter is flagged, so a resource object or
    an `Output` passed as `project` is left alone. This reaches only the
    mechanically-unambiguous subset; the wider name / path / logical-handle
    distinction is dataflow-dependent and stays with review, per
    `docs/gcp-naming.md`. A repo with no Google Cloud resources drops the rule
    through `ignore`.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for arg in _function_parameters(node):
            if arg.arg in GCP_COLLECTION_NOUNS and _is_str_annotation(arg.annotation):
                yield Violation(
                    arg.lineno,
                    arg.col_offset + 1,
                    RS_GCP_BARE_IDENTIFIER,
                    f"parameter '{arg.arg}' holds a bare Google Cloud resource "
                    f"identifier; name it '{arg.arg}_id'",
                )


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


def disfavored_gcp_terms_in_prose(text: str) -> Iterator[tuple[int, str, str]]:
    """Yields each disfavored Google Cloud term in a run of prose text.

    Reports a `(offset, found, preferred)` triple for every whole-word match of
    a term in `DISFAVORED_GCP_TERMS`, where `offset` is the match's 0-based
    position in `text`, `found` is the text as written, and `preferred` is the
    current form to write, skipping a match already in its exact preferred
    form. Backtick code spans and URIs are blanked to equal-length whitespace
    first, so a term in code font (`gcp.storage`) or inside a URL is left alone
    and the reported offsets still index the original `text`. Unlike RS049's
    length-preserving recasing, a replacement changes length, so a caller
    rewriting in place applies the triples in reverse offset order. Shared by
    RS050's docstring and comment checks.
    """
    masked = _blank_prose_spans(text)
    for match in _GCP_TERM_PATTERN.finditer(masked):
        found = match.group()
        normalized = re.sub(r"\s+", " ", found).upper()
        preferred = _GCP_TERM_REPLACEMENT[normalized]
        # A disfavored key can differ from its preferred form in case alone
        # (`BigTable` to `Bigtable`), and the scan is case-insensitive, so the
        # already-correct form matches its own key; leave it be.
        if found == preferred:
            continue
        yield match.start(), found, preferred


def _blank_prose_spans(text: str) -> str:
    """Replaces each backtick span and URI in `text` with equal-length spaces.

    Keeping the run's length preserves every other character's offset, so a
    token position found in the blanked text indexes the original `text`.
    """
    without_spans = _BACKTICK_SPAN_PATTERN.sub(
        lambda match: " " * len(match.group()), text
    )
    return _PROSE_URI.sub(lambda match: " " * len(match.group()), without_spans)


@lru_cache(maxsize=128)
def effective_prose_acronyms(pyproject: Path | None) -> dict[str, str]:
    """Returns the uppercased-to-canonical acronym map RS049 corrects prose to.

    The map is the shipped acronyms plus `acronyms-extra` minus
    `acronyms-exclude`, keyed by each entry's uppercased form and valued by its
    canonical casing (`IPV6` to `IPv6`, `NAT` to `NAT`). A shipped acronym
    whose lowercased form collides with an English word or shorthand (`SMART`,
    `ID`) is dropped, so prose is not miscorrected; an `acronyms-extra` entry
    is kept even when it names such a collision, so a repo that means it can
    reintroduce one. An acronym a prose term-map rule owns (`GCP`, which RS050
    rewrites to `Google Cloud`) is dropped unconditionally, `acronyms-extra`
    included. RS001 shares the same config keys but keeps the full set, since a
    CapWords identifier is unambiguously code where prose is not.
    """
    table = _repostyle_table(pyproject)
    extra = _string_list(table, "acronyms-extra")
    exclude = frozenset(
        word.upper() for word in _string_list(table, "acronyms-exclude")
    )
    canonical_casing: dict[str, str] = {}
    for word in ACRONYMS:
        key = word.upper()
        if (
            key not in exclude
            and key not in _PROSE_AMBIGUOUS_ACRONYMS
            and key not in _PROSE_TERM_OWNED_ACRONYMS
        ):
            canonical_casing[key] = word
    for word in extra:
        key = word.upper()
        if key not in exclude and key not in _PROSE_TERM_OWNED_ACRONYMS:
            canonical_casing[key] = word
    return canonical_casing


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
    for word in _identifier_words(name):
        if word in BANNED_ABBREVIATIONS:
            yield Violation(
                lineno,
                col_offset + 1,
                RS_BANNED_ABBREVIATION,
                f"'{name}' uses the abbreviation '{word}'; spell the word out",
            )


def _acronym_named_targets(node: ast.AST) -> Iterator[tuple[str, int, int]]:
    """Yields the at-most-one casing-checked name a node introduces.

    Resolves a class name, PEP 695 alias or type parameter, or a
    `TypeVar`-family factory assignment to its `(name, lineno, col_offset)`
    triple; yields nothing for any other node.
    """
    if isinstance(node, ast.ClassDef):
        yield (node.name, node.lineno, node.col_offset)
    elif isinstance(node, _PEP695_TYPE_ALIAS):
        yield (node.name.id, node.lineno, node.col_offset)
    elif isinstance(node, _PEP695_TYPE_PARAMS):
        yield (node.name, node.lineno, node.col_offset)
    elif isinstance(node, ast.Assign):
        yield from _typevar_factory_targets(node)


def _acronym_violations(
    name: str, lineno: int, col_offset: int, acronyms: frozenset[str]
) -> Iterator[Violation]:
    """Yields a casing violation for each miscased acronym in a CapWords name.

    A name not starting with an uppercase letter is left alone.
    """
    if not name[:1].isupper():
        return
    for acronym in _capwords_acronym_violations(name, acronyms):
        yield Violation(
            lineno,
            col_offset + 1,
            RS_ACRONYM_CASING,
            f"acronym '{acronym}' must stay uppercase in '{name}'",
        )


def _boolean_prefix_named_targets(node: ast.AST) -> Iterator[tuple[str, int, int]]:
    """Yields the at-most-one annotated boolean name a node introduces.

    Resolves a `bool`-annotated parameter or a `bool`-annotated variable or
    attribute target to its `(name, lineno, col_offset)` triple; yields nothing
    for any other node.
    """
    if isinstance(node, ast.arg) and _is_bool_annotation(node.annotation):
        yield (node.arg, node.lineno, node.col_offset)
    elif isinstance(node, ast.AnnAssign) and _is_bool_annotation(node.annotation):
        yield from _name_and_position(node.target)


def _boolean_prefix_violations(
    name: str, lineno: int, col_offset: int
) -> Iterator[Violation]:
    """Yields a violation when a boolean name's first word is not a prefix.

    The accepted prefixes are `is`, `has`, `can`, and `should`.
    """
    first = next(_identifier_words(name), None)
    if first is not None and first not in BOOLEAN_PREFIXES:
        yield Violation(
            lineno,
            col_offset + 1,
            RS_BOOLEAN_PREFIX_REQUIRED,
            f"boolean '{name}' should read as a yes/no question; prefix it "
            f"with is, has, can, or should",
        )


def _capwords_acronym_violations(name: str, acronyms: frozenset[str]) -> Iterator[str]:
    for word in _CAPWORDS_WORD.findall(name):
        upper = word.upper()
        if upper in acronyms and word != upper:
            yield upper


@lru_cache(maxsize=128)
def _effective_acronyms(pyproject: Path | None) -> frozenset[str]:
    """Returns the acronym set, adjusted for this repo's config.

    A repo adds a domain acronym through `acronyms-extra` — a DICOM repo adds
    `UID`, `SCU`, `PACS` — or drops one too aggressive for its own names
    through `acronyms-exclude`, tuning RS001 locally instead of editing the
    shared list every repo inherits, the same extend-and-exclude pattern
    RS034's `imperative-verbs-extra` and `imperative-verbs-exclude` use over
    its own shipped set. Entries are matched uppercased, so their case in
    config does not matter.
    """
    table = _repostyle_table(pyproject)
    extra = _string_list(table, "acronyms-extra")
    exclude = frozenset(
        word.upper() for word in _string_list(table, "acronyms-exclude")
    )
    if not extra and not exclude:
        return _ACRONYM_SET
    return frozenset(
        word.upper() for word in (*ACRONYMS, *extra) if word.upper() not in exclude
    )


def _negated_boolean_named_targets(node: ast.AST) -> Iterator[tuple[str, int, int]]:
    """Yields the at-most-one boolean-checked name a node introduces.

    Resolves a function or method name, a parameter, or a store-context `Name`
    target to its `(name, lineno, col_offset)` triple; yields nothing for any
    other node. Class names, attributes, and imports are out of scope.
    """
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        yield (node.name, node.lineno, node.col_offset)
    elif isinstance(node, ast.arg):
        yield (node.arg, node.lineno, node.col_offset)
    elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
        yield (node.id, node.lineno, node.col_offset)


def _negated_boolean_violations(
    name: str, lineno: int, col_offset: int
) -> Iterator[Violation]:
    """Yields a violation if a boolean-prefixed name embeds a negation word."""
    words = list(_identifier_words(name))
    if len(words) < 2 or words[0] not in BOOLEAN_PREFIXES:
        return
    negation = next((word for word in words[1:] if word in NEGATION_WORDS), None)
    if negation is not None:
        yield Violation(
            lineno,
            col_offset + 1,
            RS_NO_NEGATED_BOOLEAN,
            f"boolean '{name}' embeds '{negation}'; name the positive "
            f"and negate at the call site",
        )


def _identifier_words(name: str) -> Iterator[str]:
    """Yields the lowercased words composing a snake_case or CapWords name."""
    for part in name.split("_"):
        for word in _CAPWORDS_WORD.findall(part):
            yield word.lower()


def _is_bool_annotation(annotation: ast.expr | None) -> bool:
    """Reports whether an annotation is the bare `bool` type."""
    return isinstance(annotation, ast.Name) and annotation.id == "bool"


# The stringized (forward-reference) annotations RS051 reads as a string type,
# whitespace removed so `str | None` matches whatever the author's spacing.
_STR_FORWARD_REFS: frozenset[str] = frozenset(
    {"str", "str|None", "None|str", "Optional[str]"}
)


def _function_parameters(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> Iterator[ast.arg]:
    """Yields a function's positional and keyword parameters.

    The `*args` and `**kwargs` catch-alls are left out, since neither is named
    for a single resource.
    """
    yield from node.args.posonlyargs
    yield from node.args.args
    yield from node.args.kwonlyargs


def _is_dunder(name: str) -> bool:
    """Reports whether a name is a double-underscore special method."""
    return name.startswith("__") and name.endswith("__")


def _is_property_setter(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Reports whether a definition is a `@<property>.setter`.

    A setter's name is fixed by the property it backs, so it is out of the
    author's control the way an override's is.
    """
    return any(
        isinstance(decorator, ast.Attribute) and decorator.attr == "setter"
        for decorator in node.decorator_list
    )


def _is_str_annotation(annotation: ast.expr | None) -> bool:
    """Reports whether an annotation declares a plain string type.

    Accepts `str`, `str | None`, and `Optional[str]`, resolving a stringized
    forward reference (`"str"`) and the `None` arm of a union too. Anything
    else — another type, a `list[str]`, or no annotation — reads as
    not-a-string, so RS051 fires only where the parameter is declared to hold a
    plain string.
    """
    if isinstance(annotation, ast.Name):
        return annotation.id == "str"
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        return annotation.value.replace(" ", "") in _STR_FORWARD_REFS
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        return _is_str_annotation(annotation.left) or _is_str_annotation(
            annotation.right
        )
    if isinstance(annotation, ast.Subscript) and _is_optional_name(annotation.value):
        return _is_str_annotation(annotation.slice)
    return False


def _is_optional_name(node: ast.expr) -> bool:
    """Reports whether a subscript base is `Optional` or `typing.Optional`."""
    if isinstance(node, ast.Name):
        return node.id == "Optional"
    return isinstance(node, ast.Attribute) and node.attr == "Optional"


def _name_and_position(target: ast.expr) -> Iterator[tuple[str, int, int]]:
    """Yields a name or attribute target's name with its position.

    Yields nothing for any other target, such as a tuple or subscript.
    """
    if isinstance(target, ast.Name):
        yield (target.id, target.lineno, target.col_offset)
    elif isinstance(target, ast.Attribute):
        yield (target.attr, target.lineno, target.col_offset)


def _typevar_factory_targets(node: ast.Assign) -> Iterator[tuple[str, int, int]]:
    """Yields the string-literal name of a TypeVar-family factory call.

    Requires the assigned value to be a recognized factory call whose first
    argument is a string constant; yields that name with the assignment's
    position, or nothing otherwise.
    """
    call = node.value
    if not isinstance(call, ast.Call):
        return
    factory = _typevar_factory_name(call)
    if (
        factory is not None
        and call.args
        and isinstance(call.args[0], ast.Constant)
        and isinstance(call.args[0].value, str)
    ):
        yield (call.args[0].value, node.lineno, node.col_offset)


def _typevar_factory_name(call: ast.Call) -> str | None:
    """Returns a TypeVar-family factory call's unqualified name, if any."""
    func = call.func
    if isinstance(func, ast.Name):
        return func.id if func.id in _TYPE_FACTORY_NAMES else None
    if isinstance(func, ast.Attribute):
        return func.attr if func.attr in _TYPE_FACTORY_NAMES else None
    return None
