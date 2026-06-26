"""Identifier-naming rules: acronym casing, abbreviations, suffixes, booleans."""

from __future__ import annotations

import ast
import re
import tomllib
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from pystyle.rules._shared import (
    TEST_CLASS_PATTERN,
    _is_test_file,
    _parse_python,
    find_pyproject,
)
from pystyle.rules._violation import (
    RS_ACRONYM_CASING,
    RS_BANNED_ABBREVIATION,
    RS_BOOLEAN_PREFIX_REQUIRED,
    RS_DISCOURAGED_CLASS_SUFFIX,
    RS_EXCEPTION_ALIAS,
    RS_NO_MAKE_IN_PRODUCTION,
    RS_NO_NEGATED_BOOLEAN,
    RS_ONE_VERB_PER_CONCEPT,
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

# PEP 695 type-alias / type-parameter syntax parses only on Python
# 3.12+, so these AST node classes are absent on 3.11. Resolve them
# defensively to an empty tuple there: `isinstance(node, ())` is always
# False, and no PEP 695 node can appear in a 3.11 parse anyway.
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

# `exc` optionally followed by digits: the blessed `exc`, plus `exc2`,
# `exc3` for a nested handler that must not shadow an outer alias. `exc`
# is the one abbreviation exempt from RS010, since it is the universal
# Python idiom for the exception in hand.
_BLESSED_EXCEPTION_ALIAS = re.compile(r"exc\d*")

_MIN_DESCRIPTIVE_ALIAS_LENGTH = 4


def check_acronym_casing(path: Path, source: str) -> Iterator[Violation]:
    """Flag CapWords identifiers where a known acronym is not all uppercase.

    Scope: class names, PEP 695 `type` aliases, PEP 695 type parameters
    (`class C[T]`, `def f[T]`), and `TypeVar`/`NewType`/`ParamSpec`/
    `TypeVarTuple` factory calls in either `Name` or `typing.TypeVar`
    attribute form.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in ast.walk(tree):
        for name, lineno, col_offset in _acronym_named_targets(node):
            yield from _acronym_violations(name, lineno, col_offset)


def check_banned_abbreviation(path: Path, source: str) -> Iterator[Violation]:
    """Flag an introduced name that drops letters from a known word.

    Scope: class, function, and parameter names, an `as` alias on an
    import, and any assignment, loop, with-as, comprehension, or walrus
    target. The name is split into its snake_case and CapWords words,
    and a word equal to a banned abbreviation (`cfg`, `ctx`, `req`,
    `resp`, `conn`, ...) is rejected in favor of the spelled-out word.
    Attribute names and string contents are not checked, so a literal
    `"cfg"` and a third-party `response.idx` access are both left alone.
    An import without an alias is left alone too, since the imported
    name is the source module's to spell, not this file's.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in ast.walk(tree):
        for name, lineno, col_offset in _banned_named_targets(node):
            yield from _abbreviation_violations(name, lineno, col_offset)


def check_discouraged_class_suffix(path: Path, source: str) -> Iterator[Violation]:
    """Flag a class name ending in a vague agent suffix.

    `Manager`, `Helper`, `Util`, and `Utils` name what a class loosely
    does rather than what it is, and tend to accrete unrelated
    procedures; name the responsibility instead (`ConnectionPool`, not
    `ConnectionManager`). A pytest-style test class (`Test` followed by
    a capitalized word, as in `TestContextManager`) is exempt, since it
    is named for the unit under test.
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
    """Flag a boolean name that embeds its own negation.

    A name opening with a boolean prefix (`is`, `has`, `can`, `should`)
    and carrying `not` or `no` as a later word reads as a standing
    negative — `is_not_stale`, `has_no_results` — so every call site
    must double-negate it (`if not is_not_stale`). Name the positive
    (`is_fresh`, `has_results`) and negate where the value is read.
    Scope: function and method names, parameters, and names bound by
    assignment or annotation. The negation is matched only as a whole
    snake_case or CapWords word, so `is_notable` and `is_north` (where
    `not` or `no` is merely a leading substring) are left alone.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in ast.walk(tree):
        for name, lineno, col_offset in _negated_boolean_named_targets(node):
            yield from _negated_boolean_violations(name, lineno, col_offset)


def check_boolean_prefix_required(path: Path, source: str) -> Iterator[Violation]:
    """Flag a boolean name that does not read as a yes/no question.

    A boolean should answer a yes/no question, so it opens with `is`,
    `has`, `can`, or `should` (`is_finalized`, `has_results`); a bare
    `valid` or `enabled` does not. Scope: `bool`-annotated parameters
    and `bool`-annotated variable and attribute targets. Detection is by
    annotation, so an unannotated local is left alone and the signal
    stays free of guesses; a `-> bool` function is left alone too, since
    a predicate verb (`startswith`, `suppresses`) is the idiomatic name
    for one. Advisory: it marks names to reconsider rather than failing
    the run.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in ast.walk(tree):
        for name, lineno, col_offset in _boolean_prefix_targets(node):
            yield from _boolean_prefix_violations(name, lineno, col_offset)


def check_exception_alias(path: Path, source: str) -> Iterator[Violation]:
    """Flag a non-descriptive `except ... as` alias.

    A caught exception's bound name must be `exc`, `exc` followed by
    digits (`exc2`) for a nested handler, or a descriptive name of at
    least four characters (`validation_error`, `original_exc`); the
    noise aliases `e`, `ex`, and `err` are rejected. A bare `except X:`
    binding no name is left alone.
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
    """Flag a `make_` function defined outside a test module.

    `make_` is reserved for test fixtures (`make_bundle`,
    `make_patient`). In production it hides whether the call assembles
    in memory or changes the world; use `build_` for pure in-memory
    assembly or `create_` for construction with a side effect. A
    function under a `tests/` path, a `test_*` / `*_test` module, or a
    `conftest.py` is a fixture and left alone. The `make_` prefix must
    be a whole word, so `makedirs` and a bare `make` (a builder's
    terminal method) are not flagged.
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


def check_one_verb_per_concept(path: Path, source: str) -> Iterator[Violation]:
    """Flag a function whose leading verb is a banned synonym of a canonical one.

    The house style keeps one verb per concept: a repo settles on
    `fetch_` for remote retrieval and does not also reach for
    `retrieve_` or `load_` for the same act. Since which verb is
    canonical is the repo's own choice, the canonical-to-synonyms map is
    declared per repo in a `[tool.pystyle.verb-synonyms]` table, mapping
    each canonical verb to the synonyms it supplants. A function or
    method whose leading verb token (the text before the first
    underscore) equals a declared synonym is flagged in favor of the
    canonical verb. With no configured table the rule reports nothing.

    Scope is deliberately lexical: it does not judge whether a verb fits
    a function's behavior — whether a `get_` quietly does I/O, or a
    `build_` should have been `create_` — which needs reading the body
    and stays with style review. A test module and `conftest.py` are
    left alone, matching the make-in-production rule.
    """
    if _is_test_file(path) or path.name == "conftest.py":
        return
    pyproject = find_pyproject(path)
    if pyproject is None:
        return
    canonical_for = dict(_verb_synonyms(pyproject))
    if not canonical_for:
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        verb = node.name.split("_", 1)[0]
        canonical = canonical_for.get(verb)
        if canonical is not None:
            yield Violation(
                node.lineno,
                node.col_offset + 1,
                RS_ONE_VERB_PER_CONCEPT,
                f"'{node.name}' uses the verb '{verb}'; this repo uses "
                f"'{canonical}' for that concept (one verb per concept)",
            )


def _abbreviation_violations(
    name: str, lineno: int, col_offset: int
) -> Iterator[Violation]:
    """Yield a violation for each banned abbreviation among a name's words."""
    for word in _identifier_words(name):
        if word in BANNED_ABBREVIATIONS:
            yield Violation(
                lineno,
                col_offset + 1,
                RS_BANNED_ABBREVIATION,
                f"'{name}' uses the abbreviation '{word}'; spell the word out",
            )


def _acronym_named_targets(node: ast.AST) -> Iterator[tuple[str, int, int]]:
    """Yield the at-most-one casing-checked name a node introduces.

    Resolve a class name, PEP 695 alias or type parameter, or a
    TypeVar-family factory assignment to its (name, lineno, col_offset)
    triple; yield nothing for any other node.
    """
    if isinstance(node, ast.ClassDef):
        yield (node.name, node.lineno, node.col_offset)
    elif isinstance(node, _PEP695_TYPE_ALIAS):
        yield (node.name.id, node.lineno, node.col_offset)
    elif isinstance(node, _PEP695_TYPE_PARAMS):
        yield (node.name, node.lineno, node.col_offset)
    elif isinstance(node, ast.Assign):
        yield from _typevar_factory_targets(node)


def _acronym_violations(name: str, lineno: int, col_offset: int) -> Iterator[Violation]:
    """Yield a casing violation for each miscased acronym in a CapWords name.

    A name not starting with an uppercase letter is left alone.
    """
    if not name[:1].isupper():
        return
    for acronym in _capwords_acronym_violations(name):
        yield Violation(
            lineno,
            col_offset + 1,
            RS_ACRONYM_CASING,
            f"acronym '{acronym}' must stay uppercase in '{name}'",
        )


def _banned_named_targets(node: ast.AST) -> Iterator[tuple[str, int, int]]:
    """Yield the at-most-one abbreviation-checked name a node introduces.

    Resolve a class, function, or parameter name, an aliased import, or
    a store-context `Name` target to its (name, lineno, col_offset)
    triple; yield nothing for any other node.
    """
    if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
        yield (node.name, node.lineno, node.col_offset)
    elif isinstance(node, ast.arg):
        yield (node.arg, node.lineno, node.col_offset)
    elif isinstance(node, ast.alias) and node.asname is not None:
        yield (node.asname, node.lineno, node.col_offset)
    elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
        yield (node.id, node.lineno, node.col_offset)


def _boolean_prefix_targets(node: ast.AST) -> Iterator[tuple[str, int, int]]:
    """Yield the at-most-one annotated boolean name a node introduces.

    Resolve a `bool`-annotated parameter or a `bool`-annotated variable
    or attribute target to its (name, lineno, col_offset) triple; yield
    nothing for any other node.
    """
    if isinstance(node, ast.arg) and _is_bool_annotation(node.annotation):
        yield (node.arg, node.lineno, node.col_offset)
    elif isinstance(node, ast.AnnAssign) and _is_bool_annotation(node.annotation):
        yield from _name_and_position(node.target)


def _boolean_prefix_violations(
    name: str, lineno: int, col_offset: int
) -> Iterator[Violation]:
    """Yield a violation when a boolean name's first word is not a prefix.

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


def _capwords_acronym_violations(name: str) -> Iterator[str]:
    for word in _CAPWORDS_WORD.findall(name):
        upper = word.upper()
        if upper in _ACRONYM_SET and word != upper:
            yield upper


def _negated_boolean_named_targets(node: ast.AST) -> Iterator[tuple[str, int, int]]:
    """Yield the at-most-one boolean-checked name a node introduces.

    Resolve a function or method name, a parameter, or a store-context
    `Name` target to its (name, lineno, col_offset) triple; yield
    nothing for any other node. Class names, attributes, and imports are
    out of scope.
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
    """Yield a violation if a boolean-prefixed name embeds a negation word."""
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
    """Yield the lowercased words composing a snake_case or CapWords name."""
    for part in name.split("_"):
        for word in _CAPWORDS_WORD.findall(part):
            yield word.lower()


def _is_bool_annotation(annotation: ast.expr | None) -> bool:
    """Report whether an annotation is the bare `bool` type."""
    return isinstance(annotation, ast.Name) and annotation.id == "bool"


def _name_and_position(target: ast.expr) -> Iterator[tuple[str, int, int]]:
    """Yield a name or attribute target's name with its position.

    Yield nothing for any other target, such as a tuple or subscript.
    """
    if isinstance(target, ast.Name):
        yield (target.id, target.lineno, target.col_offset)
    elif isinstance(target, ast.Attribute):
        yield (target.attr, target.lineno, target.col_offset)


def _typevar_factory_targets(node: ast.Assign) -> Iterator[tuple[str, int, int]]:
    """Yield the string-literal name of a TypeVar-family factory call.

    Require the assigned value to be a recognized factory call whose
    first argument is a string constant; yield that name with the
    assignment's position, or nothing otherwise.
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
    """Return the unqualified name of a TypeVar-family factory call, if any."""
    func = call.func
    if isinstance(func, ast.Name):
        return func.id if func.id in _TYPE_FACTORY_NAMES else None
    if isinstance(func, ast.Attribute):
        return func.attr if func.attr in _TYPE_FACTORY_NAMES else None
    return None


@lru_cache(maxsize=128)
def _verb_synonyms(pyproject: Path) -> tuple[tuple[str, str], ...]:
    """Read the `verb-synonyms` table as (synonym, canonical) pairs.

    Each `canonical = [synonyms...]` entry under
    `[tool.pystyle.verb-synonyms]` is flattened into one pair per
    synonym, so a leading verb can be looked up against its canonical
    replacement.
    """
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return ()
    table = data.get("tool", {}).get("pystyle", {}).get("verb-synonyms", {})
    return tuple(
        (synonym, canonical)
        for canonical, synonyms in table.items()
        for synonym in synonyms
    )
