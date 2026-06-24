"""Element-ordering rule: warn when module and class members are out of order.

This enforces a project *convention*, not a standard. PEP 8 and the
Google style guide deliberately decline to mandate the order of
constants, classes, and functions within a module, so the default order
here is the one this package holds itself to — module-level helpers
before the public callable they support, class members from constructor
down to private methods — and each scope's order is overridable per repo
through `[tool.gradient-pystyle]`.

The rule reports, it never reorders. A rewriter would have to honour
definition-before-use (a base class, decorator, or default argument must
precede the name that reads it at definition time); a checker sidesteps
that, and additionally suppresses a finding whose only fix would move an
element past a name it reads at definition time, so it never asks for an
edit that would not run.
"""

from __future__ import annotations

import ast
import tomllib
from collections.abc import Callable, Iterator
from functools import lru_cache
from pathlib import Path

from gradient_pystyle.rules._shared import _parse_python, find_pyproject
from gradient_pystyle.rules._violation import RS_ELEMENT_ORDER, Violation

# Default module order, helpers-first: private definitions sit above the
# public surface they support, the layout this package itself follows.
DEFAULT_MODULE_ORDER = (
    "docstring",
    "future_import",
    "dunder",
    "import",
    "constant",
    "private",
    "public",
    "main",
)
# Default class-body order, public surface before private, following the
# flake8-class-attributes-order convention.
DEFAULT_CLASS_ORDER = (
    "docstring",
    "field",
    "init",
    "dunder",
    "property",
    "staticmethod",
    "classmethod",
    "method",
    "private_method",
)

_LABELS = {
    "docstring": "docstring",
    "future_import": "`__future__` import",
    "dunder": "module dunder",
    "import": "import",
    "constant": "module constant",
    "private": "private helper",
    "public": "public class or function",
    "main": "`__main__` block",
    "field": "class field",
    "init": "constructor",
    "property": "property",
    "staticmethod": "static method",
    "classmethod": "class method",
    "method": "method",
    "private_method": "private method",
}
# Decorator names that re-categorise a method, in priority order.
_PROPERTY_DECORATORS = frozenset({"property", "cached_property", "setter", "deleter"})


@lru_cache(maxsize=128)
def _configured_order(
    pyproject: Path, key: str, default: tuple[str, ...]
) -> tuple[str, ...]:
    """Read an ordered category list from a pyproject file, or the default.

    An empty list disables ranking for that scope (every category
    floats), so a repo turns one scope off without ignoring the whole
    rule.
    """
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return default
    value = data.get("tool", {}).get("gradient-pystyle", {}).get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return default
    return tuple(value)


def _is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def _assign_targets(stmt: ast.Assign | ast.AnnAssign) -> list[str]:
    if isinstance(stmt, ast.AnnAssign):
        return [stmt.target.id] if isinstance(stmt.target, ast.Name) else []
    return [t.id for t in stmt.targets if isinstance(t, ast.Name)]


def _is_main_guard(test: ast.expr) -> bool:
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "__name__"
    )


def _is_string_expr(stmt: ast.stmt) -> bool:
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    )


def _assignment_category(stmt: ast.Assign | ast.AnnAssign) -> str:
    """Categorise a module-level assignment as a dunder or a constant."""
    names = _assign_targets(stmt)
    if names and all(_is_dunder(name) for name in names):
        return "dunder"
    return "constant"


def _definition_category(
    stmt: ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
) -> str:
    """Categorise a top-level definition as private or public by its name."""
    private = stmt.name.startswith("_") and not _is_dunder(stmt.name)
    return "private" if private else "public"


def _module_category(stmt: ast.stmt, first: bool) -> str | None:
    """Return the ordering category for a top-level statement, or None.

    A None category is opaque — a `TYPE_CHECKING`/`try` guard or
    anything unrecognised — and never constrains the order around it.
    """
    if _is_string_expr(stmt):
        return "docstring" if first else None
    if isinstance(stmt, ast.ImportFrom) and stmt.module == "__future__":
        return "future_import"
    if isinstance(stmt, ast.Import | ast.ImportFrom):
        return "import"
    if isinstance(stmt, ast.If):
        return "main" if _is_main_guard(stmt.test) else None
    if isinstance(stmt, ast.Assign | ast.AnnAssign):
        return _assignment_category(stmt)
    if isinstance(stmt, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
        return _definition_category(stmt)
    return None


def _decorator_names(stmt: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Names a method's decorators read — `setter`/`deleter` via attribute."""
    names: set[str] = set()
    for decorator in stmt.decorator_list:
        node = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


def _method_category(stmt: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Categorise a method by its decorator, then its name."""
    decorators = _decorator_names(stmt)
    if decorators & _PROPERTY_DECORATORS:
        return "property"
    if "staticmethod" in decorators:
        return "staticmethod"
    if "classmethod" in decorators:
        return "classmethod"
    if stmt.name in {"__new__", "__init__", "__post_init__"}:
        return "init"
    if _is_dunder(stmt.name):
        return "dunder"
    return "private_method" if stmt.name.startswith("_") else "method"


def _class_category(stmt: ast.stmt, first: bool) -> str | None:
    """Return the ordering category for a class-body statement, or None.

    A property and its setter/deleter all land in `property`, so the
    same-name cluster shares a rank and is never split by the order.
    """
    if _is_string_expr(stmt):
        return "docstring" if first else None
    if isinstance(stmt, ast.Assign | ast.AnnAssign):
        return "field"
    if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef):
        return _method_category(stmt)
    return None


def _defined_names(stmt: ast.stmt) -> set[str]:
    """Names a statement binds in its enclosing namespace."""
    if isinstance(stmt, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
        return {stmt.name}
    if isinstance(stmt, ast.Assign | ast.AnnAssign):
        return set(_assign_targets(stmt))
    if isinstance(stmt, ast.Import | ast.ImportFrom):
        return {alias.asname or alias.name.split(".")[0] for alias in stmt.names}
    return set()


def _definition_time_refs(stmt: ast.stmt) -> set[str]:
    """Names a statement reads when its definition executes, not when called.

    A function or class body runs only on call or instantiation, so
    names used there impose no order. Decorators, base classes, and
    default arguments are evaluated when the `def`/`class` runs, so they
    do.
    """
    nodes: list[ast.AST] = []
    if isinstance(stmt, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
        nodes.extend(stmt.decorator_list)
    if isinstance(stmt, ast.ClassDef):
        nodes.extend(stmt.bases)
        nodes.extend(keyword.value for keyword in stmt.keywords)
    if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef):
        defaults = (*stmt.args.defaults, *stmt.args.kw_defaults)
        nodes.extend(default for default in defaults if default is not None)
    if isinstance(stmt, ast.Assign):
        nodes.append(stmt.value)
    if isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
        nodes.append(stmt.value)
    refs: set[str] = set()
    for node in nodes:
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
                refs.add(child.id)
    return refs


def _order_violations(
    body: list[ast.stmt],
    categorize: Callable[[ast.stmt, bool], str | None],
    order: tuple[str, ...],
) -> Iterator[Violation]:
    """Yield a finding for each statement that sits below its category's rank.

    A statement is reported only when moving it up to its rank would
    keep definition-before-use intact — it reads no name defined above
    it in the span it would jump, and nothing in that span reads a name
    it defines.
    """
    rank = {name: index for index, name in enumerate(order)}
    categories = [categorize(stmt, index == 0) for index, stmt in enumerate(body)]
    defines = [_defined_names(stmt) for stmt in body]
    refs = [_definition_time_refs(stmt) for stmt in body]

    highest_rank = -1
    highest_index = -1
    for index, (stmt, category) in enumerate(zip(body, categories, strict=True)):
        if category is None or category not in rank:
            continue
        if rank[category] >= highest_rank:
            highest_rank, highest_index = rank[category], index
            continue
        span = range(highest_index, index)
        blockers = set().union(*(defines[k] for k in span))
        if refs[index] & blockers:
            continue
        if any(refs[k] & defines[index] for k in span):
            continue
        yield Violation(
            stmt.lineno,
            stmt.col_offset + 1,
            RS_ELEMENT_ORDER,
            f"{_LABELS.get(category, category)} appears after "
            f"{_LABELS.get(categories[highest_index], categories[highest_index])} "
            f"(line {body[highest_index].lineno}); group it with its kind earlier",
        )


def check_module_element_order(path: Path, source: str) -> Iterator[Violation]:
    """Flag a top-level element that sits below its category's place.

    Constants belong above the definitions that follow them, helpers
    above the public surface, the `__main__` guard last. The order is
    the configured `module-order`, defaulting to a helpers-first layout.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    pyproject = find_pyproject(path)
    order = (
        _configured_order(pyproject, "module-order", DEFAULT_MODULE_ORDER)
        if pyproject is not None
        else DEFAULT_MODULE_ORDER
    )
    yield from _order_violations(tree.body, _module_category, order)


def check_class_member_order(path: Path, source: str) -> Iterator[Violation]:
    """Flag a class member that sits below its category's place.

    Each class body is checked against the configured `class-order`
    (defaulting to fields, constructor, dunders, properties, then
    static, class, public, and private methods); a property and its
    setter stay one cluster. Required-before-default field order is
    never touched.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    pyproject = find_pyproject(path)
    order = (
        _configured_order(pyproject, "class-order", DEFAULT_CLASS_ORDER)
        if pyproject is not None
        else DEFAULT_CLASS_ORDER
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            yield from _order_violations(node.body, _class_category, order)
