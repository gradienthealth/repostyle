"""Identifier rules.

Acronym casing, banned abbreviations, vague class suffixes, boolean naming, the
`make_`-in-production ban, and exception-alias naming.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from repostyle._shared import (
    _parse_python,
    _repostyle_table,
    _string_list,
    _walk_tree,
    find_pyproject,
)
from repostyle.rules._violation import (
    RS_ACRONYM_CASING,
    Violation,
)
from repostyle.rules.naming_abbreviations import (
    BANNED_ABBREVIATIONS as BANNED_ABBREVIATIONS,
)
from repostyle.rules.naming_abbreviations import (
    CAPWORDS_WORD_PATTERN,
)
from repostyle.rules.naming_abbreviations import (
    check_banned_abbreviation as check_banned_abbreviation,
)
from repostyle.rules.naming_abbreviations import (
    miscased_acronyms_in_prose as miscased_acronyms_in_prose,
)
from repostyle.rules.naming_boole import (
    check_boolean_prefix_required as check_boolean_prefix_required,
)
from repostyle.rules.naming_boole import (
    check_no_negated_boolean as check_no_negated_boolean,
)
from repostyle.rules.naming_boole import (
    check_predicate_function_naming as check_predicate_function_naming,
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

_CANONICAL_ACRONYMS: dict[str, str] = {word.upper(): word for word in ACRONYMS}

_ACRONYM_SET = frozenset(_CANONICAL_ACRONYMS)

_PROSE_AMBIGUOUS_ACRONYMS: frozenset[str] = frozenset({"ID", "SMART"})

_PROSE_TERM_OWNED_ACRONYMS: frozenset[str] = frozenset({"GCP"})

_TYPE_FACTORY_NAMES = frozenset({"TypeVar", "NewType", "ParamSpec", "TypeVarTuple"})

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
    for node in _walk_tree(tree):
        for name, lineno, col_offset in _acronym_named_targets(node):
            yield from _acronym_violations(name, lineno, col_offset, acronyms)


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


def _capwords_acronym_violations(name: str, acronyms: frozenset[str]) -> Iterator[str]:
    for word in CAPWORDS_WORD_PATTERN.findall(name):
        upper = word.upper()
        if upper in acronyms and word != upper:
            yield upper


@lru_cache(maxsize=128)
def _effective_acronyms(pyproject: Path | None) -> frozenset[str]:
    """Returns the acronym set, adjusted for this repo's config.

    A repo adds a domain acronym through `acronyms-extra` -- a DICOM repo adds
    `UID`, `SCU`, `PACS` -- or drops one too aggressive for its own names
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
