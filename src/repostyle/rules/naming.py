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

from repostyle.rules._shared import (
    TEST_CLASS_PATTERN,
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
    RS_NO_MAKE_IN_PRODUCTION,
    RS_NO_NEGATED_BOOLEAN,
    Violation,
)

ACRONYMS: tuple[str, ...] = (
    "API",
    "DOB",
    "FHIR",
    "GCP",
    "HTTP",
    "ID",
    "JSON",
    "JWT",
    "MRN",
    "SMART",
    "URL",
)

_CAPWORDS_WORD = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+")
_ACRONYM_SET = frozenset(ACRONYMS)

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

DISCOURAGED_CLASS_SUFFIXES: tuple[str, ...] = ("Helper", "Manager", "Util", "Utils")

BOOLEAN_PREFIXES: frozenset[str] = frozenset({"can", "has", "is", "should"})

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
    shared list every repo inherits, the same override pattern RS017's
    `banned-imports` and RS034's `imperative-verbs-extra` already use. Entries
    are matched uppercased, so their case in config does not matter.
    """
    table = _repostyle_table(pyproject)
    extra = _string_list(table, "acronyms-extra")
    exclude = _string_list(table, "acronyms-exclude")
    if not extra and not exclude:
        return _ACRONYM_SET
    excluded = frozenset(word.upper() for word in exclude)
    return frozenset(
        word.upper() for word in (*ACRONYMS, *extra) if word.upper() not in excluded
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
