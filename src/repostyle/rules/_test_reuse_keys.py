"""Binding-aware syntax keys for test-reuse analysis."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from repostyle.rules._test_reuse_context import (
    _ImportContext,
    _ReuseFunction,
    _TestFunction,
)

_SCALAR_TYPES = (type(None), bool, int, float, complex, str, bytes)


def _function_key(
    function: _ReuseFunction, *, should_preserve_parameter_names: bool
) -> object:
    """Returns a binding-aware key for a helper or fixture."""
    bindings = _function_bindings(
        function.node,
        should_preserve_parameter_names=should_preserve_parameter_names,
    )
    body_state = _NormalizationState(function.context, bindings)
    definition_state = _NormalizationState(function.context, {})
    return (
        isinstance(function.node, ast.AsyncFunctionDef),
        _arguments_key(
            function.node.args,
            body_state,
            should_preserve_names=should_preserve_parameter_names,
            expression_state=definition_state,
        ),
        tuple(
            _node_key(decorator, definition_state)
            for decorator in function.node.decorator_list
        ),
        _node_key(function.node.returns, definition_state),
        tuple(
            _node_key(statement, body_state)
            for statement in _without_docstring(function.node.body)
        ),
    )


def _parametrization_key(function: _ReuseFunction) -> tuple[object, tuple[str, ...]]:
    """Returns the literal-abstracted test key and encountered values."""
    bindings = _function_bindings(function.node, should_preserve_parameter_names=True)
    signature_state = _NormalizationState(function.context, bindings)
    definition_state = _NormalizationState(function.context, {})
    body_state = _NormalizationState(
        function.context, bindings, should_abstract_literals=True
    )
    key = (
        function.scope,
        isinstance(function.node, ast.AsyncFunctionDef),
        _arguments_key(
            function.node.args,
            signature_state,
            should_preserve_names=True,
            expression_state=definition_state,
        ),
        tuple(
            _node_key(decorator, definition_state)
            for decorator in function.node.decorator_list
        ),
        _node_key(function.node.returns, definition_state),
        tuple(
            _node_key(statement, body_state)
            for statement in _without_docstring(function.node.body)
        ),
    )
    return key, tuple(body_state.literal_values)


def _arguments_key(
    arguments: ast.arguments,
    state: _NormalizationState,
    *,
    should_preserve_names: bool,
    expression_state: _NormalizationState,
) -> object:
    """Returns a signature shape with exact defaults and annotations."""

    def argument_key(argument: ast.arg) -> object:
        name = argument.arg if should_preserve_names else state.bindings[argument.arg]
        return (
            name,
            _node_key(argument.annotation, expression_state),
            argument.type_comment,
        )

    return (
        tuple(argument_key(item) for item in arguments.posonlyargs),
        tuple(argument_key(item) for item in arguments.args),
        argument_key(arguments.vararg) if arguments.vararg else None,
        tuple(argument_key(item) for item in arguments.kwonlyargs),
        tuple(_node_key(item, expression_state) for item in arguments.kw_defaults),
        argument_key(arguments.kwarg) if arguments.kwarg else None,
        tuple(_node_key(item, expression_state) for item in arguments.defaults),
    )


def _setup_prefix(function: _ReuseFunction) -> tuple[tuple[object, ...], int | None]:
    """Returns leading assignment keys and the first call-bearing value."""
    bindings = _function_bindings(function.node, should_preserve_parameter_names=True)
    state = _NormalizationState(function.context, bindings)
    prefix: list[object] = []
    first_call_assignment: int | None = None
    for statement in _without_docstring(function.node.body):
        value = _simple_assignment_value(statement)
        if value is None:
            break
        prefix.append(_node_key(statement, state))
        if first_call_assignment is None and any(
            isinstance(child, ast.Call) for child in ast.walk(value)
        ):
            first_call_assignment = len(prefix)
    return tuple(prefix), first_call_assignment


def _function_bindings(
    node: _TestFunction, *, should_preserve_parameter_names: bool
) -> dict[str, str]:
    """Assigns stable identities to parameters and local bindings."""
    bindings: dict[str, str] = {}
    groups = (
        ("posonly", node.args.posonlyargs),
        ("arg", node.args.args),
        ("kwonly", node.args.kwonlyargs),
    )
    for kind, arguments in groups:
        for index, argument in enumerate(arguments):
            bindings[argument.arg] = (
                argument.arg if should_preserve_parameter_names else f"{kind}:{index}"
            )
    if node.args.vararg:
        bindings[node.args.vararg.arg] = (
            node.args.vararg.arg if should_preserve_parameter_names else "vararg"
        )
    if node.args.kwarg:
        bindings[node.args.kwarg.arg] = (
            node.args.kwarg.arg if should_preserve_parameter_names else "kwarg"
        )
    collector = _BindingCollector(bindings)
    for statement in node.body:
        collector.visit(statement)
    return bindings


def _simple_assignment_value(statement: ast.stmt) -> ast.expr | None:
    """Returns the value of a supported simple assignment."""
    if isinstance(statement, ast.Assign):
        if len(statement.targets) == 1 and isinstance(statement.targets[0], ast.Name):
            return statement.value
    elif (
        isinstance(statement, ast.AnnAssign)
        and isinstance(statement.target, ast.Name)
        and statement.value is not None
    ):
        return statement.value
    return None


def _without_docstring(statements: list[ast.stmt]) -> list[ast.stmt]:
    """Returns body statements after an optional leading docstring."""
    if statements and isinstance(statements[0], ast.Expr):
        value = statements[0].value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return statements[1:]
    return statements


class _BindingCollector(ast.NodeVisitor):
    """Collects function-local names in source traversal order."""

    def __init__(self, bindings: dict[str, str]) -> None:
        self.bindings = bindings

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Stops at a nested async scope."""

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Stops at a nested class scope."""

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        """Records an exception target before visiting its body."""
        if node.name and node.name not in self.bindings:
            self.bindings[node.name] = f"local:{len(self.bindings)}"
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Stops at a nested scope."""

    def visit_Name(self, node: ast.Name) -> None:
        """Records a stored name once."""
        if isinstance(node.ctx, ast.Store | ast.Del) and node.id not in self.bindings:
            self.bindings[node.id] = f"local:{len(self.bindings)}"


@dataclass
class _NormalizationState:
    """Carries name bindings and literal collection through one syntax key."""

    context: _ImportContext
    bindings: dict[str, str]
    should_abstract_literals: bool = False
    is_inside_joined_string: bool = False
    literal_values: list[str] = field(default_factory=list)


def _node_key(node: object, state: _NormalizationState) -> object:
    """Returns a hashable syntax key without source positions."""
    if node is None or isinstance(node, str | int | float | complex | bytes | bool):
        return node
    if isinstance(node, list):
        return tuple(_node_key(item, state) for item in node)
    if isinstance(node, ast.AST):
        return _ast_node_key(node, state)
    return repr(node)


def _ast_node_key(node: ast.AST, state: _NormalizationState) -> object:
    """Returns the custom syntax key for one AST node."""
    if isinstance(node, ast.Name):
        identity = (
            ("bound", state.bindings[node.id])
            if node.id in state.bindings
            else state.context.external_name(node.id)
        )
        return ("Name", identity, type(node.ctx).__name__)
    if isinstance(node, ast.Constant):
        if (
            state.should_abstract_literals
            and not state.is_inside_joined_string
            and isinstance(node.value, _SCALAR_TYPES)
            and not _is_multiline_string(node.value)
        ):
            state.literal_values.append(repr(node.value))
            return ("Constant", type(node.value).__name__, "<value>")
        return ("Constant", type(node.value).__name__, node.value, node.kind)
    if isinstance(node, ast.JoinedStr):
        previous = state.is_inside_joined_string
        state.is_inside_joined_string = True
        try:
            return (
                "JoinedStr",
                tuple(_node_key(value, state) for value in node.values),
            )
        finally:
            state.is_inside_joined_string = previous
    if isinstance(node, ast.ExceptHandler):
        name = state.bindings.get(node.name, node.name) if node.name else None
        return (
            "ExceptHandler",
            _node_key(node.type, state),
            name,
            tuple(_node_key(item, state) for item in node.body),
        )
    fields = tuple(
        (field_name, _node_key(value, state))
        for field_name, value in ast.iter_fields(node)
    )
    return (type(node).__name__, fields)


def _is_multiline_string(value: object) -> bool:
    """Reports whether a literal carries structured, multi-line test input."""
    newline = b"\n" if isinstance(value, bytes) else "\n"
    return isinstance(value, str | bytes) and newline in value
