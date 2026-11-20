"""Constructor parameters a class only forwards into one collaborator.

A parameter is forwarded when every read of it, directly or through the `self`
attribute `__init__` stores it on, passes it unchanged into constructor calls
of one resolvable first-party class. RS073 reads this analysis to find a class
that builds a collaborator from settings it should not hold.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from repostyle.rules._class_index import ClassFacts, MethodDef, PackageIndex, methods


@dataclass
class ForwardingAnalysis:
    """The forwarded constructor parameters of a package's classes."""

    index: PackageIndex
    """The package's class index, which resolves each constructor call."""
    _forwarded: dict[str, _Forwarded] = field(default_factory=dict)

    def chain_depth(self, name: str, param: str, seen: frozenset[str]) -> int:
        """Counts the constructors a forwarded parameter passes through.

        A cycle stops at the first class it revisits.
        """
        forwards = self.forwarded_params(name).get(param)
        if not forwards or name in seen:
            return 0
        targets = {
            (forward.target, forward.target_param)
            for forward in forwards
            if forward.target_param is not None
        }
        deeper = [
            self.chain_depth(target, target_param, seen | {name})
            for target, target_param in targets
        ]
        return 1 + max(deeper, default=0)

    def forwarded_params(self, name: str) -> _Forwarded:
        """Maps each `__init__` parameter of `name` it only forwards.

        A class without its own `__init__`, such as a dataclass record,
        forwards nothing: its fields are its state, and deriving another record
        from them is not plumbing.
        """
        if name not in self._forwarded:
            facts = self.index.classes.get(name)
            init = None if facts is None else facts.init
            self._forwarded[name] = (
                {}
                if facts is None or init is None
                else _forwarded_params(facts, init, self.index)
            )
        return self._forwarded[name]


def _forwarded_params(
    facts: ClassFacts, init: MethodDef, index: PackageIndex
) -> _Forwarded:
    """Finds the `__init__` parameters a class only forwards to one class."""
    parents = {
        child: parent
        for parent in ast.walk(facts.node)
        for child in ast.iter_child_nodes(parent)
    }
    reads, writes = _self_attribute_uses(facts, parents, index)
    forwarded: _Forwarded = {}
    for param in facts.params:
        names = list(_param_names(init, param))
        if any(not isinstance(node.ctx, ast.Load) for node in names):
            continue
        uses = [_classify(node, parents, index, facts.path) for node in names]
        resolved = _resolve_uses(uses, reads, writes)
        if resolved and len({forward.target for forward in resolved}) == 1:
            forwarded[param] = resolved
    return forwarded


def _param_names(init: MethodDef, param: str) -> Iterator[ast.Name]:
    """Yields each occurrence of `param` in `__init__` that refers to it.

    A nested function, lambda, or comprehension that binds the same name
    shadows the parameter, so its occurrences are skipped.
    """
    pending: list[ast.AST] = list(init.body)
    while pending:
        node = pending.pop()
        if _rebinds(node, param):
            continue
        if isinstance(node, ast.Name) and node.id == param:
            yield node
        pending.extend(ast.iter_child_nodes(node))


def _rebinds(node: ast.AST, name: str) -> bool:
    """Reports whether a nested scope binds `name` itself."""
    if isinstance(node, ast.Lambda | ast.FunctionDef | ast.AsyncFunctionDef):
        arguments = node.args
        declared = [
            *arguments.posonlyargs,
            *arguments.args,
            *arguments.kwonlyargs,
            *filter(None, [arguments.vararg, arguments.kwarg]),
        ]
        return any(argument.arg == name for argument in declared)
    if isinstance(node, ast.ListComp | ast.SetComp | ast.GeneratorExp | ast.DictComp):
        return any(
            isinstance(target, ast.Name) and target.id == name
            for generator in node.generators
            for target in ast.walk(generator.target)
        )
    return False


def _self_attribute_uses(
    facts: ClassFacts, parents: dict[ast.AST, ast.AST], index: PackageIndex
) -> tuple[_AttributeReads, dict[str, int]]:
    """Classifies every read of a `self` attribute and counts its writes."""
    reads: _AttributeReads = {}
    writes: dict[str, int] = {}
    for method in methods(facts.node):
        for node in ast.walk(method):
            if (attribute := _self_attribute(node)) is None:
                continue
            if not isinstance(node.ctx, ast.Load):  # type: ignore[attr-defined]
                writes[attribute] = writes.get(attribute, 0) + 1
                continue
            use = _classify(node, parents, index, facts.path)  # type: ignore[arg-type]
            reads.setdefault(attribute, []).append(
                use if isinstance(use, _Forward) else None
            )
    return reads, writes


def _classify(
    node: ast.expr, parents: dict[ast.AST, ast.AST], index: PackageIndex, path: Path
) -> _Use:
    """Classifies one read of a value inside a class.

    Returns a `_Forward` when the read passes the value unchanged into a
    resolvable constructor, the attribute name when it stores the value on
    `self`, and `None` for any other use.
    """
    parent = parents.get(node)
    if isinstance(parent, ast.Assign | ast.AnnAssign) and parent.value is node:
        targets = parent.targets if isinstance(parent, ast.Assign) else [parent.target]
        return _self_attribute(targets[0]) if len(targets) == 1 else None
    if isinstance(parent, ast.keyword) and parent.arg is not None:
        call = parents.get(parent)
        if isinstance(call, ast.Call) and (facts := index.resolve(call, path)):
            return _Forward(facts.node.name, parent.arg)
        return None
    if isinstance(parent, ast.Call) and node in parent.args:
        if (facts := index.resolve(parent, path)) is None:
            return None
        return _Forward(facts.node.name, _positional_param(parent, node, facts))
    return None


def _positional_param(call: ast.Call, node: ast.expr, facts: ClassFacts) -> str | None:
    """Names the parameter a positional argument binds, when it is known."""
    position = call.args.index(node)
    if position >= len(facts.positional) or any(
        isinstance(argument, ast.Starred) for argument in call.args[:position]
    ):
        return None
    return facts.positional[position]


def _resolve_uses(
    uses: list[_Use], reads: _AttributeReads, writes: dict[str, int]
) -> list[_Forward]:
    """Returns a parameter's forwards, or nothing when any use consumes it.

    A store on a private `self` attribute stands for every read of it. A store
    on a public attribute consumes the value, since code outside the class can
    read it, and so does an attribute that is never read or is written more
    than once.
    """
    forwards: list[_Forward] = []
    for use in uses:
        expanded = [use]
        if isinstance(use, str):
            is_private = use.startswith("_")
            if not is_private or not reads.get(use) or writes.get(use, 0) != 1:
                return []
            expanded = reads[use]
        if any(not isinstance(item, _Forward) for item in expanded):
            return []
        forwards.extend(item for item in expanded if isinstance(item, _Forward))
    return forwards


def _self_attribute(node: ast.AST) -> str | None:
    """Returns `attr` when `node` is `self.attr`, otherwise `None`."""
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    ):
        return node.attr
    return None


@dataclass(frozen=True)
class _Forward:
    """One argument passed unchanged into a resolved constructor call."""

    target: str
    """The name of the class the call constructs."""
    target_param: str | None
    """The constructor parameter receiving the value, when it is known."""


# How one read of a value is used: a forward, a store on the named `self`
# attribute, or `None` for any other use.
_Use = _Forward | str | None
# Each forwarded parameter of a class, mapped to its forwards
_Forwarded = dict[str, list[_Forward]]
# The classified reads of each `self` attribute
_AttributeReads = dict[str, list[_Use]]
