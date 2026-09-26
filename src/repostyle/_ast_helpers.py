"""Shared Python-AST helpers."""

from __future__ import annotations

import ast


def has_decorator(
    node: ast.FunctionDef | ast.AsyncFunctionDef, names: frozenset[str] | set[str]
) -> bool:
    """Reports whether the definition carries a decorator named in `names`.

    Match both the bare (`@override`) and dotted (`@typing.override`) forms,
    comparing only the final attribute name, and see through a decorator call
    (`@cache()`) to the name it applies.
    """
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Name) and target.id in names:
            return True
        if isinstance(target, ast.Attribute) and target.attr in names:
            return True
    return False
