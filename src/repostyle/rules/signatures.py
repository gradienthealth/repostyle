"""Signature-shape rule: flag a definition with too many positional arguments.

A long positional parameter list makes a call site a row of bare values
whose meaning depends on order, and reordering or inserting a parameter
silently rebinds every caller. The house style answers this with
keyword-only dependency-injection builders (`build_fhir_client(*,
...)`), whose arguments are named at the call site and
order-independent, so this rule counts only the positional parameters
and leaves keyword-only ones uncounted.

This rule is a stand-in for ruff's `PLR0917` (`too-many-positional-
arguments`), which is preview-gated in the pinned ruff version and so
cannot be selected without turning on `preview` globally for every
consuming repo. It mirrors `PLR0917`'s semantics — the default cap of
five, counting positional-only and positional-or-keyword parameters
while excluding the implicit `self`/`cls` of a method and exempting an
`@override`. When `PLR0917` graduates to stable in the pinned ruff
version, select it in `ruff-base.toml` and delete this rule (PROC-2319).
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

from repostyle.rules._shared import _has_decorator, _parse_python
from repostyle.rules._violation import RS_TOO_MANY_POSITIONAL_ARGS, Violation

# Matches ruff PLR0917's default `max-positional-args`. A definition with more
# positional parameters than this is flagged.
MAX_POSITIONAL_ARGS = 5

_OVERRIDE_DECORATORS = frozenset({"override"})


def check_too_many_positional_args(path: Path, source: str) -> Iterator[Violation]:
    """Flags a definition with more than the allowed positional arguments.

    Counts a definition's positional-only and positional-or-keyword parameters;
    keyword-only parameters (those after a `*`) never count, so a keyword-only
    dependency-injection builder is left alone however many it declares. The
    implicit `self`/`cls` of an instance or class method is not counted, and a
    method decorated with `@override` is exempt. A definition over the cap is
    reported at its `def` line.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    yield from _check_scope(tree, is_within_class=False)


def _check_scope(node: ast.AST, is_within_class: bool) -> Iterator[Violation]:
    """Walks one scope, tracking whether its definitions are class methods.

    A function defined directly in a class body binds an implicit `self`/`cls`,
    so its first positional parameter is excluded; a nested function or a
    module-level one does not, so descending into a function body resets the
    class context.
    """
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
            yield from _check_function(child, is_within_class)
            yield from _check_scope(child, is_within_class=False)
        elif isinstance(child, ast.ClassDef):
            yield from _check_scope(child, is_within_class=True)
        else:
            yield from _check_scope(child, is_within_class)


def _check_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef, is_within_class: bool
) -> Iterator[Violation]:
    if _has_decorator(node, _OVERRIDE_DECORATORS):
        return
    is_method = is_within_class and not _has_decorator(node, {"staticmethod"})
    count = _positional_count(node, is_method)
    if count > MAX_POSITIONAL_ARGS:
        yield Violation(
            node.lineno,
            node.col_offset + 1,
            RS_TOO_MANY_POSITIONAL_ARGS,
            f"function '{node.name}' has {count} positional parameters; over "
            f"the limit of {MAX_POSITIONAL_ARGS}, make the extra ones "
            "keyword-only after a `*`",
        )


def _positional_count(
    node: ast.FunctionDef | ast.AsyncFunctionDef, is_method: bool
) -> int:
    """Counts the positional parameters, excluding a method's `self`/`cls`."""
    positional = node.args.posonlyargs + node.args.args
    count = len(positional)
    if is_method and positional:
        count -= 1
    return count
