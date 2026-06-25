"""Identifier-naming rules: acronym casing, abbreviations, suffixes."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

from pystyle.rules._shared import TEST_CLASS_PATTERN, _parse_python
from pystyle.rules._violation import (
    RS_ACRONYM_CASING,
    RS_BANNED_ABBREVIATION,
    RS_DISCOURAGED_CLASS_SUFFIX,
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


def _capwords_acronym_violations(name: str) -> Iterator[str]:
    for word in _CAPWORDS_WORD.findall(name):
        upper = word.upper()
        if upper in _ACRONYM_SET and word != upper:
            yield upper


def _identifier_words(name: str) -> Iterator[str]:
    """Yield the lowercased words composing a snake_case or CapWords name."""
    for part in name.split("_"):
        for word in _CAPWORDS_WORD.findall(part):
            yield word.lower()


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
