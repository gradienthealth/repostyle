"""Internal doc-value implementation partition 3."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

from repostyle._shared import _has_decorator, _is_test_file, _parse_python, _walk_tree
from repostyle.rules._doc_value_impl_4 import (
    internal_entries,
    internal_group_by_section,
)


def internal_raised_exception_types(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[str]:
    """Lists the specific exception types the function's own body raises.

    Collects the class name of every `raise SomeError(...)` or `raise
    SomeError` statement reachable in the body without crossing into a nested
    function, lambda, or class, so a raise belonging to an inner scope is not
    attributed here. A bare `raise` and a `raise` of a lowercase expression
    (a caught alias, a factory call result) name no class and are skipped. A
    dotted `raise pkg.mod.FooError()` is reduced to its final segment. Each
    name is listed once, in first-encounter order.
    """
    names: list[str] = []
    stack: list[ast.AST] = list(reversed(node.body))
    while stack:
        child = stack.pop()
        if isinstance(
            child, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda | ast.ClassDef
        ):
            continue
        if isinstance(child, ast.Raise) and child.exc is not None:
            name = _exception_type_name(child.exc)
            if name is not None and name not in names:
                names.append(name)
        stack.extend(reversed(list(ast.iter_child_nodes(child))))
    return names


def _exception_type_name(exc: ast.expr) -> str | None:
    """Returns the class name a `raise` target names, or `None`.

    A raised `Call` unwraps to its callee, so `raise FooError(...)` and `raise
    FooError` both resolve to `FooError`; a dotted `pkg.FooError` resolves to
    its final attribute. A target whose name does not start with a capital -- a
    re-raised alias like `exc`, or a lowercase factory call -- is treated as
    not naming a specific type and returns `None`.
    """
    call = exc.func if isinstance(exc, ast.Call) else exc
    if isinstance(call, ast.Name) and call.id[:1].isupper():
        return call.id
    if isinstance(call, ast.Attribute) and call.attr[:1].isupper():
        return call.attr
    return None


def internal_has_positive_raise_verb(clause: str) -> bool:
    """Reports whether the clause holds a raise verb in a non-negated spot.

    Each raise-verb occurrence is checked against the text directly before it,
    so `never re-raises` reads as negated while a later, unqualified `raises`
    in the same clause still counts.
    """
    return any(
        not _RAISE_NEGATION_PATTERN.search(clause[: match.start()])
        for match in _RAISE_VERB_PATTERN.finditer(clause)
    )


_RAISE_VERB_PATTERN = re.compile(
    "\\b(?:re-?)?rais(?:e[sd]?|ing)\\b|\\bpropagat(?:e[sd]?|ing)\\b", re.IGNORECASE
)

_RAISE_NEGATION_PATTERN = re.compile(
    "\\b(?:never|not|cannot|without|instead\\s+of|rather\\s+than|no\\s+longer)\\s+(?:be(?:ing)?\\s+)?$",
    re.IGNORECASE,
)


def internal_has_return_annotation(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    """Reports whether the return annotation is present and not `None`."""
    annotation = node.returns
    if annotation is None:
        return False
    return not (isinstance(annotation, ast.Constant) and annotation.value is None)


def internal_param_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Counts a function's parameters, excluding a leading `self`/`cls`."""
    return len(internal_param_names(node))


def internal_param_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Lists a function's parameter names, excluding a leading `self`/`cls`."""
    args = node.args
    positional = args.posonlyargs + args.args
    names = [arg.arg for arg in positional + args.kwonlyargs]
    if args.vararg is not None:
        names.append(args.vararg.arg)
    if args.kwarg is not None:
        names.append(args.kwarg.arg)
    if positional and positional[0].arg in ("self", "cls"):
        names = names[1:]
    return names


def internal_public_functions(
    path: Path, source: str
) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Yields each public, non-test function in a parseable source file.

    A definition is in scope when the file is not a test module and the
    function is neither underscore- nor `test_`-prefixed nor an `@overload`
    stub -- the shared subject both documentation-value rules inspect.
    """
    if _is_test_file(path):
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in _walk_tree(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if node.name.startswith(("_", "test_")):
            continue
        if _has_decorator(node, {"overload"}):
            continue
        yield node


def internal_returns_multi_element_tuple(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    """Reports whether the return annotation is a multi-element `tuple`.

    A multi-element `tuple` is an anonymous composite whose parts a single
    summary line cannot enumerate, so it warrants a `Returns:` section. The
    variadic `tuple[X, ...]` form is a homogeneous sequence, not a composite,
    and is excluded.
    """
    annotation = node.returns
    if not isinstance(annotation, ast.Subscript):
        return False
    base = annotation.value
    name = base.id if isinstance(base, ast.Name) else getattr(base, "attr", None)
    if name not in ("tuple", "Tuple"):
        return False
    if not isinstance(annotation.slice, ast.Tuple):
        return False
    elements = annotation.slice.elts
    last = elements[-1] if elements else None
    if isinstance(last, ast.Constant) and last.value is Ellipsis:
        return False
    return len(elements) >= 2


def internal_split_docstring(docstring: str) -> tuple[str, set[str], set[str]]:
    """Splits a cleaned docstring into body prose and documented names.

    Args:
        docstring: The cleaned docstring to inspect.

    Returns:
        The body prose, documented parameters, and documented exceptions.
    """
    sections = internal_group_by_section(docstring)
    body = "\n".join(sections.get(None, ()))
    documented_args = internal_entries(sections, _ARGS_CAPTIONS, _ARG_ENTRY_PATTERN)
    documented_raises = {
        name.rpartition(".")[2]
        for name in internal_entries(sections, {"Raises"}, _RAISES_ENTRY_PATTERN)
    }
    return (body, documented_args, documented_raises)


_ARG_ENTRY_PATTERN = re.compile("^[ \\t]+\\*{0,2}(\\w+)\\s*(?:\\([^)]*\\))?\\s*:")

_RAISES_ENTRY_PATTERN = re.compile("^[ \\t]+([\\w.]+)\\s*:")

_ARGS_CAPTIONS = frozenset({"Args", "Arguments", "Keyword Args", "Keyword Arguments"})
