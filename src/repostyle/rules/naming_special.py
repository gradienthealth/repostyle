"""Focused helpers extracted from a larger rule module."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

from repostyle._shared import (
    TEST_CLASS_PATTERN,
    _blank_prose_spans,
    _is_test_file,
    _parse_python,
    _walk_tree,
)
from repostyle.rules._violation import (
    RS_DISCOURAGED_CLASS_SUFFIX,
    RS_EXCEPTION_ALIAS,
    RS_GCP_BARE_IDENTIFIER,
    RS_NO_MAKE_IN_PRODUCTION,
    Violation,
)

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
_GCP_TERM_REPLACEMENT: dict[str, str] = {
    re.sub(r"\s+", " ", term).upper(): preferred
    for term, preferred in DISFAVORED_GCP_TERMS.items()
}
_GCP_TERM_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:"
    + "|".join(
        r"\s+".join(re.escape(word) for word in term.split())
        for term in sorted(DISFAVORED_GCP_TERMS, key=len, reverse=True)
    )
    + r")(?![A-Za-z0-9_-])(?!\.[A-Za-z0-9])",
    re.IGNORECASE,
)
GCP_COLLECTION_NOUNS: frozenset[str] = frozenset(
    {"project", "bucket", "dataset", "topic", "subscription", "instance"}
)
DISCOURAGED_CLASS_SUFFIXES: tuple[str, ...] = ("Helper", "Manager", "Util", "Utils")
_BLESSED_EXCEPTION_ALIAS = re.compile(r"exc\d*")
_MIN_DESCRIPTIVE_ALIAS_LENGTH = 4


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
    for node in _walk_tree(tree):
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
    for node in _walk_tree(tree):
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
    for node in _walk_tree(tree):
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
    `instance`) almost always holds that resource's bare id rather than its
    qualified `{collection}/{id}` name. The `_id` suffix (`project` to
    `project_id`) states which of the two the value carries, so a caller reads
    the intent without tracing the dataflow. Only a string-typed parameter is
    flagged, so a resource object or an `Output` passed as `project` is left
    alone. This reaches only the mechanically-unambiguous subset; the wider
    name / path / logical-handle distinction is dataflow-dependent and stays
    with review, per `docs/gcp-naming.md`. A repo with no Google Cloud
    resources drops the rule through `ignore`.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in _walk_tree(tree):
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


def _is_str_annotation(annotation: ast.expr | None) -> bool:
    """Reports whether an annotation declares a plain string type.

    Accepts `str`, `str | None`, and `Optional[str]`, resolving a stringized
    forward reference (`"str"`) and the `None` arm of a union too. Anything
    else -- another type, a `list[str]`, or no annotation -- reads as
    not-a-string, so RS051 fires only where the parameter is declared to hold a
    plain string.
    """
    if isinstance(annotation, ast.Name):
        return annotation.id == "str"
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        return annotation.value.replace(" ", "") in _STR_FORWARD_REFS
    if isinstance(annotation, ast.BinOp) and isinstance(annotation.op, ast.BitOr):
        arms = (annotation.left, annotation.right)
        return any(_is_str_annotation(arm) for arm in arms) and all(
            _is_str_annotation(arm) or _is_none_constant(arm) for arm in arms
        )
    if isinstance(annotation, ast.Subscript) and _is_optional_name(annotation.value):
        return _is_str_annotation(annotation.slice)
    return False


def _is_none_constant(annotation: ast.expr) -> bool:
    """Reports whether an annotation node is the bare `None` literal.

    RS051 accepts a `str | None` union but not, say, `str | int`, so the `None`
    arm has to be told apart from any other non-`str` type sharing a union.
    """
    return isinstance(annotation, ast.Constant) and annotation.value is None


def _is_optional_name(node: ast.expr) -> bool:
    """Reports whether a subscript base is `Optional` or `typing.Optional`."""
    if isinstance(node, ast.Name):
        return node.id == "Optional"
    return isinstance(node, ast.Attribute) and node.attr == "Optional"
