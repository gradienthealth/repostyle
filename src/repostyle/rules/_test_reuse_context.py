"""Conservative name and import resolution for test-reuse analysis."""

from __future__ import annotations

import ast
import builtins
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

_TestFunction = ast.AsyncFunctionDef | ast.FunctionDef
_BUILTINS = frozenset(dir(builtins))
_DYNAMIC_NAMES = frozenset({"eval", "exec", "globals", "locals", "vars"})
_UNSUPPORTED_REUSE_NODES = (
    ast.DictComp,
    ast.GeneratorExp,
    ast.Global,
    ast.Lambda,
    ast.ListComp,
    ast.Match,
    ast.NamedExpr,
    ast.Nonlocal,
    ast.SetComp,
)


@dataclass(frozen=True)
class _ImportContext:
    """Carries the external identities visible to one module."""

    imports: dict[str, str]
    module_bindings: frozenset[str]
    rebound_names: frozenset[str]
    path: Path
    has_wildcard_import: bool

    def external_name(self, name: str) -> tuple[str, str]:
        """Returns the conservative identity of a non-local name.

        Returns:
            The identity category and its qualified or file-specific value.
        """
        if name in self.imports:
            return ("import", self.imports[name])
        if name in self.module_bindings:
            return ("module", f"{self.path}:{name}")
        if self.has_wildcard_import:
            return ("global", f"{self.path}:{name}")
        if name in _BUILTINS:
            return ("builtin", name)
        return ("global", f"{self.path}:{name}")


@dataclass(frozen=True)
class _ReuseFunction:
    """Pairs one candidate function with its module identities."""

    node: _TestFunction
    path: Path
    scope: str
    context: _ImportContext

    @property
    def qualified_name(self) -> str:
        """Returns the class-qualified function name."""
        return f"{self.scope}.{self.node.name}" if self.scope else self.node.name


def _import_context(tree: ast.Module, path: Path) -> _ImportContext:
    """Returns the conservative module identities visible from `path`."""
    imports = _direct_imports(tree, path)
    rebound_names = _rebound_module_names(tree)
    for name in rebound_names:
        imports.pop(name, None)
    return _ImportContext(
        imports,
        frozenset(_module_bindings(tree)),
        frozenset(rebound_names),
        path,
        _has_wildcard_import(tree),
    )


def _direct_imports(tree: ast.Module, path: Path) -> dict[str, str]:
    """Returns direct module imports keyed by their bound names."""
    return dict(
        binding
        for statement in tree.body
        for binding in _direct_import_bindings(statement, path)
    )


def _direct_import_bindings(
    statement: ast.stmt, path: Path
) -> Iterator[tuple[str, str]]:
    """Yields bound names and identities from one direct import."""
    if isinstance(statement, ast.Import):
        for alias in statement.names:
            bound = alias.asname or alias.name.split(".", 1)[0]
            yield bound, alias.name if alias.asname else bound
    elif isinstance(statement, ast.ImportFrom):
        origin = _import_from_origin(statement, path)
        for alias in statement.names:
            if alias.name != "*":
                yield alias.asname or alias.name, f"{origin}.{alias.name}"


def _import_from_origin(statement: ast.ImportFrom, path: Path) -> str:
    """Returns a path-aware origin for an imported name."""
    if statement.level == 0:
        return statement.module or ""
    package = list(path.with_suffix("").parts[:-1])
    parents = statement.level - 1
    if parents > len(package):
        return f"{path}:relative:{statement.level}:{statement.module or ''}"
    if parents:
        package = package[:-parents]
    if statement.module:
        package.extend(statement.module.split("."))
    return ".".join(package)


class _ModuleBindingCollector(ast.NodeVisitor):
    """Collects module bindings without entering nested scopes."""

    def __init__(self) -> None:
        self.names: set[str] = set()
        self.counts: Counter[str] = Counter()
        self.has_wildcard_import = False

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Records the async definition name without entering its scope."""
        self._record(node.name)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Records the class name without entering its scope."""
        self._record(node.name)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Records the definition name without entering its scope."""
        self._record(node.name)

    def visit_Import(self, node: ast.Import) -> None:
        """Records imports nested in module control flow."""
        for alias in node.names:
            self._record(alias.asname or alias.name.split(".", 1)[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Records imports nested in module control flow."""
        for alias in node.names:
            if alias.name == "*":
                self.has_wildcard_import = True
            else:
                self._record(alias.asname or alias.name)

    def visit_MatchAs(self, node: ast.MatchAs) -> None:
        """Records a pattern capture and visits its nested pattern."""
        if node.name:
            self._record(node.name)
        self.generic_visit(node)

    def visit_MatchMapping(self, node: ast.MatchMapping) -> None:
        """Records a mapping rest capture and visits nested patterns."""
        if node.rest:
            self._record(node.rest)
        self.generic_visit(node)

    def visit_MatchStar(self, node: ast.MatchStar) -> None:
        """Records a starred pattern capture."""
        if node.name:
            self._record(node.name)

    def visit_Name(self, node: ast.Name) -> None:
        """Records assignment targets."""
        if isinstance(node.ctx, ast.Store | ast.Del):
            self._record(node.id)

    def _record(self, name: str) -> None:
        """Records one module binding occurrence."""
        self.names.add(name)
        self.counts[name] += 1


def _has_wildcard_import(tree: ast.Module) -> bool:
    """Reports whether module execution can bind names through `import *`."""
    direct = any(
        isinstance(statement, ast.ImportFrom)
        and any(alias.name == "*" for alias in statement.names)
        for statement in tree.body
    )
    return direct or _module_binding_collector(tree).has_wildcard_import


def _module_bindings(tree: ast.Module) -> set[str]:
    """Returns every name bound directly in a module."""
    return _raw_imports(tree) | _module_binding_collector(tree).names


def _raw_imports(tree: ast.Module) -> set[str]:
    """Returns names introduced by direct module imports."""
    return {
        alias.asname or alias.name.split(".", 1)[0]
        for statement in tree.body
        if isinstance(statement, ast.Import | ast.ImportFrom)
        for alias in statement.names
        if alias.name != "*"
    }


def _rebound_module_names(tree: ast.Module) -> set[str]:
    """Returns names whose module identity can change during definition."""
    direct_imports = Counter(
        alias.asname or alias.name.split(".", 1)[0]
        for statement in tree.body
        if isinstance(statement, ast.Import | ast.ImportFrom)
        for alias in statement.names
        if alias.name != "*"
    )
    collector = _module_binding_collector(tree)
    counts = direct_imports + collector.counts
    return {name for name, count in counts.items() if count > 1}


def _module_binding_collector(tree: ast.Module) -> _ModuleBindingCollector:
    """Returns bindings introduced outside direct module imports."""
    collector = _ModuleBindingCollector()
    for statement in tree.body:
        if not isinstance(statement, ast.Import | ast.ImportFrom):
            collector.visit(statement)
    return collector


def _unsupported_reuse(function: _ReuseFunction) -> bool:
    """Reports whether a function exceeds conservative matching boundaries."""
    if any(
        isinstance(child, ast.Name)
        and isinstance(child.ctx, ast.Load)
        and child.id in function.context.rebound_names
        for expression in _definition_time_expressions(function.node)
        for child in ast.walk(expression)
    ):
        return True
    for child in ast.walk(function.node):
        if child is function.node:
            continue
        if isinstance(child, ast.expr) and _dynamic_namespace_reference(
            child, function.context
        ):
            return True
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            return True
        if isinstance(child, (*_UNSUPPORTED_REUSE_NODES, ast.Import, ast.ImportFrom)):
            return True
    return False


def _definition_time_expressions(node: _TestFunction) -> Iterator[ast.expr]:
    """Yields expressions evaluated while a function is defined."""
    yield from node.decorator_list
    if node.returns is not None:
        yield node.returns
    arguments = node.args
    for argument in (
        *arguments.posonlyargs,
        *arguments.args,
        *arguments.kwonlyargs,
    ):
        if argument.annotation is not None:
            yield argument.annotation
    if arguments.vararg and arguments.vararg.annotation is not None:
        yield arguments.vararg.annotation
    if arguments.kwarg and arguments.kwarg.annotation is not None:
        yield arguments.kwarg.annotation
    yield from arguments.defaults
    yield from (item for item in arguments.kw_defaults if item is not None)


def _dynamic_namespace_reference(expression: ast.expr, context: _ImportContext) -> bool:
    """Reports a callable reference that can inspect dynamic namespaces."""
    if isinstance(expression, ast.Name):
        if not isinstance(expression.ctx, ast.Load):
            return False
        if expression.id in _DYNAMIC_NAMES:
            return True
        identity = context.imports.get(expression.id, "")
    elif isinstance(expression, ast.Attribute):
        identity = _decorator_name(expression, context)
    else:
        return False
    return any(identity == f"builtins.{name}" for name in _DYNAMIC_NAMES)


def _is_fixture(node: _TestFunction, context: _ImportContext) -> bool:
    """Reports whether a function carries a fixture decorator."""
    return any(
        _decorator_tail(decorator) == "fixture"
        or _decorator_name(decorator, context) in {"fixture", "pytest.fixture"}
        or _decorator_name(decorator, context).endswith(".fixture")
        for decorator in node.decorator_list
    )


def _is_parametrized(node: _TestFunction, context: _ImportContext) -> bool:
    """Reports whether a test already carries parametrization."""
    return any(
        _decorator_tail(decorator) == "parametrize"
        or _decorator_name(decorator, context) == "parametrize"
        or _decorator_name(decorator, context).endswith(".parametrize")
        for decorator in node.decorator_list
    )


def _decorator_name(node: ast.expr, context: _ImportContext) -> str:
    """Returns a straightforward qualified expression identity."""
    expression = node.func if isinstance(node, ast.Call) else node
    if isinstance(expression, ast.Name):
        return context.external_name(expression.id)[1]
    if isinstance(expression, ast.Attribute):
        base = _decorator_name(expression.value, context)
        return f"{base}.{expression.attr}" if base else expression.attr
    return ""


def _decorator_tail(node: ast.expr) -> str:
    """Returns the final syntactic name of a decorator expression."""
    expression = node.func if isinstance(node, ast.Call) else node
    if isinstance(expression, ast.Name):
        return expression.id
    if isinstance(expression, ast.Attribute):
        return expression.attr
    return ""
