"""Element-ordering rule: define before use, then order the free choices.

Two structural conventions, both derived from the code itself rather
than from names. A module-level definition must appear before the
definitions that reference it (define-before-use), so a reader meets a
name's meaning before its use; mutual-recursion cycles are exempt
because no such order exists. Where the dependency graph leaves the
order free — adjacent private helpers or classes that do not reference
each other — they go alphabetically, the one tie-break that stays stable
as bodies change.

Within a class, methods run dunders, then public, then private, with the
public and private runs alphabetical; an enum whose members all carry
explicit literal values orders them alphabetically too. Public functions
and module constants are left to the author: a public surface often has
a narrative order, and constants carry implicit orders (a numeric id
sequence, say) that a name sort would destroy.
"""

from __future__ import annotations

import ast
import symtable
from collections.abc import Iterator
from pathlib import Path

from gradient_pystyle.rules._shared import _parse_python
from gradient_pystyle.rules._violation import RS_ELEMENT_ORDER, Violation

_ENUM_BASES = frozenset({"Enum", "IntEnum", "StrEnum", "Flag", "IntFlag", "ReprEnum"})
_DefNode = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef


def _collect_global_refs(table: symtable.SymbolTable) -> set[str]:
    """Return the module globals a symbol table and its nested scopes read.

    `symtable` resolves each name against its scope, so a parameter or
    local that shadows a module name is not reported — only true global
    references are, which keeps the dependency graph free of phantom
    edges.
    """
    names = {symbol.get_name() for symbol in table.get_symbols() if symbol.is_global()}
    for child in table.get_children():
        names |= _collect_global_refs(child)
    return names


def _is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def _alpha_kind(stmt: ast.stmt) -> str | None:
    """Return the alphabetised kind of a statement, or None to leave it free.

    Private helper functions and classes are alphabetised where the
    dependency graph allows; public functions, constants, and pytest
    test classes (ordered to mirror their subjects, not by name) are
    not.
    """
    if isinstance(stmt, ast.ClassDef):
        return None if stmt.name.startswith("Test") else "class"
    if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef):
        if stmt.name.startswith("_") and not _is_dunder(stmt.name):
            return "private helper"
    return None


def _enum_member_names(node: ast.ClassDef) -> list[str] | None:
    """Return an enum's member names if every value is an explicit literal.

    Return None when the class is not an enum or any member takes a
    computed value (`auto()`, an expression), since reordering would
    then change the values it assigns.
    """
    bases = {base.id for base in node.bases if isinstance(base, ast.Name)}
    bases |= {b.attr for b in node.bases if isinstance(b, ast.Attribute)}
    if not bases & _ENUM_BASES:
        return None
    members: list[str] = []
    for stmt in node.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            target, value = stmt.target.id, stmt.value
        elif (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
        ):
            target, value = stmt.targets[0].id, stmt.value
        else:
            continue
        if _is_dunder(target):
            continue
        if not isinstance(value, ast.Constant):
            return None
        members.append(target)
    return members


def _enum_member_order(node: ast.ClassDef) -> Iterator[Violation]:
    """Flag an enum with explicit values whose members are out of order."""
    members = _enum_member_names(node)
    if members is None:
        return
    for index, name in enumerate(members[1:], start=1):
        if name < members[index - 1]:
            yield Violation(
                node.lineno,
                node.col_offset + 1,
                RS_ELEMENT_ORDER,
                f"enum '{node.name}' member '{name}' is out of alphabetical "
                f"order; members with explicit values sort by name",
            )
            return


def _method_band(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Rank a method: dunders first, then public, then private."""
    if _is_dunder(node.name):
        return 0
    return 2 if node.name.startswith("_") else 1


def _method_member_order(node: ast.ClassDef) -> Iterator[Violation]:
    """Flag class methods out of band, or unsorted within a band.

    A pytest test class is left alone: its methods follow the
    happy-path, edge, error scenario order, not an alphabetical one.
    """
    if node.name.startswith("Test"):
        return
    methods = [
        stmt
        for stmt in node.body
        if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef)
    ]
    highest = 0
    for method in methods:
        band = _method_band(method)
        if band < highest:
            yield Violation(
                method.lineno,
                method.col_offset + 1,
                RS_ELEMENT_ORDER,
                f"method '{method.name}' is out of order; methods run "
                f"dunder, then public, then private",
            )
        highest = max(highest, band)
    for band in (1, 2):
        named = [m.name for m in methods if _method_band(m) == band]
        for index, name in enumerate(named[1:], start=1):
            if name < named[index - 1]:
                stmt = next(m for m in methods if m.name == name)
                yield Violation(
                    stmt.lineno,
                    stmt.col_offset + 1,
                    RS_ELEMENT_ORDER,
                    f"method '{name}' should be ordered before "
                    f"'{named[index - 1]}'; methods sort by name in a band",
                )
                break


def _reachability(deps: dict[str, frozenset[str]]) -> dict[str, set[str]]:
    """Map each name to every name it depends on, directly or transitively."""
    closure: dict[str, set[str]] = {}

    def resolve(name: str, seen: set[str]) -> set[str]:
        if name in closure:
            return closure[name]
        result: set[str] = set()
        for target in deps.get(name, ()):
            if target in seen:
                continue
            result.add(target)
            result |= resolve(target, seen | {target})
        closure[name] = result
        return result

    for name in deps:
        resolve(name, {name})
    return closure


def _strongly_connected(deps: dict[str, frozenset[str]]) -> dict[str, int]:
    """Map each name to a component id, grouping mutual-recursion cycles.

    Names that share a component depend on each other transitively, so
    define-before-use cannot order them and the check exempts edges
    between them.
    """
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    component: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    counter = [0]

    def visit(name: str) -> None:
        index[name] = low[name] = counter[0]
        counter[0] += 1
        stack.append(name)
        on_stack.add(name)
        for target in deps.get(name, ()):
            if target not in index:
                visit(target)
                low[name] = min(low[name], low[target])
            elif target in on_stack:
                low[name] = min(low[name], index[target])
        if low[name] == index[name]:
            while True:
                member = stack.pop()
                on_stack.discard(member)
                component[member] = index[name]
                if member == name:
                    break

    for name in deps:
        if name not in index:
            visit(name)
    return component


def _top_level_names(body: list[ast.stmt]) -> dict[str, ast.stmt]:
    """Map each top-level binding name to the statement that defines it."""
    names: dict[str, ast.stmt] = {}
    for stmt in body:
        if isinstance(stmt, _DefNode):
            names[stmt.name] = stmt
        elif isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    names[target.id] = stmt
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            names[stmt.target.id] = stmt
    return names


def _define_before_use(
    tree: ast.Module, deps: dict[str, frozenset[str]]
) -> Iterator[Violation]:
    """Flag a definition referenced by one that appears above it."""
    names = _top_level_names(tree.body)
    position = {name: index for index, name in enumerate(names)}
    component = _strongly_connected(deps)
    reported: set[str] = set()
    for user in names:
        for used in deps[user]:
            same_cycle = component.get(user) == component.get(used)
            if position[used] > position[user] and not same_cycle:
                if used not in reported:
                    reported.add(used)
                    stmt = names[used]
                    yield Violation(
                        stmt.lineno,
                        stmt.col_offset + 1,
                        RS_ELEMENT_ORDER,
                        f"'{used}' is used by '{user}' above it but defined "
                        f"here; define it before its first use",
                    )


def _dependency_map(
    path: Path, source: str, tree: ast.Module
) -> dict[str, frozenset[str]]:
    """Map each top-level name to the other top-level names it references.

    Function and class references resolve through `symtable`; a
    constant's references are the names its value expression reads.
    """
    names = _top_level_names(tree.body)
    children = {
        child.get_name(): child
        for child in symtable.symtable(source, str(path), "exec").get_children()
    }
    deps: dict[str, frozenset[str]] = {}
    for name, stmt in names.items():
        if isinstance(stmt, _DefNode) and name in children:
            refs = _collect_global_refs(children[name])
        else:
            refs = {
                node.id
                for node in ast.walk(stmt)
                if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
            }
        deps[name] = frozenset(refs & names.keys()) - {name}
    return deps


def _local_alphabetical(
    tree: ast.Module, deps: dict[str, frozenset[str]]
) -> Iterator[Violation]:
    """Flag adjacent same-kind definitions left unordered yet out of order."""
    nodes = _top_level_names(tree.body)
    names = list(nodes)
    reachable = _reachability(deps)
    for earlier, later in zip(names, names[1:], strict=False):
        kind = _alpha_kind(nodes[earlier])
        if kind is None or kind != _alpha_kind(nodes[later]):
            continue
        if later in reachable[earlier] or earlier in reachable[later]:
            continue
        if later < earlier:
            stmt = nodes[later]
            yield Violation(
                stmt.lineno,
                stmt.col_offset + 1,
                RS_ELEMENT_ORDER,
                f"{kind} '{later}' should be ordered before '{earlier}'; "
                f"independent {kind}s go alphabetically",
            )


def check_class_member_order(path: Path, source: str) -> Iterator[Violation]:
    """Flag class methods out of band order, or enum members out of order."""
    tree = _parse_python(path, source)
    if not isinstance(tree, ast.Module):
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            yield from _enum_member_order(node)
            yield from _method_member_order(node)


def check_module_element_order(path: Path, source: str) -> Iterator[Violation]:
    """Flag a top-level definition out of define-before-use or alpha order.

    A definition referenced by one above it is reported
    (mutual-recursion cycles exempt); adjacent independent private
    helpers or classes that are not alphabetical are reported too.
    """
    tree = _parse_python(path, source)
    if not isinstance(tree, ast.Module):
        return
    deps = _dependency_map(path, source, tree)
    yield from _define_before_use(tree, deps)
    yield from _local_alphabetical(tree, deps)
