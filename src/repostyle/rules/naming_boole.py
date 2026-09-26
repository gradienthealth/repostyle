"""Boolean and predicate identifier rules."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

from repostyle._shared import (
    _has_decorator,
    _parse_python,
    _walk_tree,
)
from repostyle.rules._violation import (
    RS_BOOLEAN_PREFIX_REQUIRED,
    RS_NO_NEGATED_BOOLEAN,
    RS_PREDICATE_FUNCTION_NAMING,
    Violation,
)
from repostyle.rules.naming_abbreviations import (
    BANNED_ABBREVIATIONS as BANNED_ABBREVIATIONS,
)
from repostyle.rules.naming_abbreviations import (
    check_banned_abbreviation as check_banned_abbreviation,
)
from repostyle.rules.naming_abbreviations import (
    identifier_words,
)
from repostyle.rules.naming_abbreviations import (
    miscased_acronyms_in_prose as miscased_acronyms_in_prose,
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

BOOLEAN_PREFIXES: frozenset[str] = frozenset({"can", "has", "is", "should"})

PREDICATE_PREFIXES: frozenset[str] = BOOLEAN_PREFIXES | frozenset({"allows", "needs"})

_PREDICATE_ESCAPE_DECORATORS: frozenset[str] = frozenset({"override", "overload"})

NEGATION_WORDS: frozenset[str] = frozenset({"no", "not"})


def check_no_negated_boolean(path: Path, source: str) -> Iterator[Violation]:
    """Flags a boolean name that embeds its own negation.

    A name opening with a boolean prefix (`is`, `has`, `can`, `should`) and
    carrying `not` or `no` as a later word reads as a standing negative --
    `is_not_stale`, `has_no_results` -- so every call site must double-negate
    it (`if not is_not_stale`). Name the positive (`is_fresh`, `has_results`)
    and negate where the value is read.
    Scope: function and method names, parameters, and names bound by assignment
    or annotation. The negation is matched only as a whole snake_case or
    CapWords word, so `is_notable` and `is_north` (where `not` or `no` is
    merely a leading substring) are left alone.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in _walk_tree(tree):
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
    for node in _walk_tree(tree):
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
    for node in _walk_tree(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            yield from _predicate_naming_violation(node)


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
    first = next(identifier_words(name), None)
    if first is not None and first not in BOOLEAN_PREFIXES:
        yield Violation(
            lineno,
            col_offset + 1,
            RS_BOOLEAN_PREFIX_REQUIRED,
            f"boolean '{name}' should read as a yes/no question; prefix it "
            f"with is, has, can, or should",
        )


def _name_and_position(target: ast.expr) -> Iterator[tuple[str, int, int]]:
    """Yields a name or attribute target's name with its position.

    Yields nothing for any other target, such as a tuple or subscript.
    """
    if isinstance(target, ast.Name):
        yield (target.id, target.lineno, target.col_offset)
    elif isinstance(target, ast.Attribute):
        yield (target.attr, target.lineno, target.col_offset)


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
    words = list(identifier_words(name))
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


def _is_bool_annotation(annotation: ast.expr | None) -> bool:
    """Reports whether an annotation is the bare `bool` type."""
    return isinstance(annotation, ast.Name) and annotation.id == "bool"


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
