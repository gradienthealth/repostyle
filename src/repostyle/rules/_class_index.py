"""An index resolving a call to the first-party class it constructs.

The plumbing rules RS073 and RS074 resolve a callee by its simple name. A name
defined by more than one first-party class or function, or one the calling
module imports from outside the package, does not resolve, so both rules under-
rather than over-report. Test modules are left out of the index, since a fake
often shares the name of the class it stands in for.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from repostyle._shared import (
    _is_test_file,
    _parse_python,
    _relative_to_pyproject,
    find_config_file,
)

# A method definition, sync or async
MethodDef = ast.FunctionDef | ast.AsyncFunctionDef


@dataclass(frozen=True)
class ClassFacts:
    """One first-party class and the constructor a call to it reaches."""

    path: Path
    """The module defining the class."""
    node: ast.ClassDef
    """The class definition."""
    params: tuple[str, ...]
    """Constructor parameters in positional order, without `self`."""
    annotations: tuple[ast.expr, ...]
    """The annotations on those parameters, in no particular order."""
    is_protocol: bool
    """Whether the class is a `Protocol`, the shape of a port."""
    init: MethodDef | None
    """The class's own `__init__`, absent for a generated constructor."""


@dataclass
class PackageIndex:
    """The package's resolvable first-party classes and module facts."""

    classes: dict[str, ClassFacts] = field(default_factory=dict)
    """Each resolvable class, keyed by its simple name."""
    ports: frozenset[str] = frozenset()
    """The simple names of the resolvable `Protocol` classes."""
    sources: list[tuple[Path, ast.Module, str]] = field(default_factory=list)
    """Each non-test module with its tree and config-relative path."""
    foreign_names: dict[Path, frozenset[str]] = field(default_factory=dict)
    """Per module, the names it imports from outside the package."""

    def port_names(self, facts: ClassFacts) -> list[str]:
        """Lists the ports a class's constructor annotations name, sorted."""
        named = {name for note in facts.annotations for name in _annotation_names(note)}
        return sorted(named & self.ports)

    def resolve(self, call: ast.Call, path: Path) -> ClassFacts | None:
        """Returns the first-party class `call` constructs, if it resolves."""
        func = call.func
        if isinstance(func, ast.Name):
            if func.id in self.foreign_names.get(path, frozenset()):
                return None
            return self.classes.get(func.id)
        if isinstance(func, ast.Attribute):
            return self.classes.get(func.attr)
        return None


def build_index(files: Sequence[tuple[Path, str]]) -> PackageIndex:
    """Indexes the resolvable first-party classes of the non-test `files`."""
    index = PackageIndex()
    class_defs: dict[str, list[ClassFacts]] = {}
    function_names: set[str] = set()
    roots = _first_party_roots(files)
    for path, source in files:
        tree = _parse_python(path, source)
        relative = _relative_to_pyproject(path, find_config_file(path))
        if not isinstance(tree, ast.Module) or _is_test_file(Path(relative)):
            continue
        index.sources.append((path, tree, relative))
        index.foreign_names[path] = _foreign_names(tree, roots)
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                class_defs.setdefault(node.name, []).append(_class_facts(path, node))
            elif isinstance(node, MethodDef):
                function_names.add(node.name)
    index.classes = {
        name: defs[0]
        for name, defs in class_defs.items()
        if len(defs) == 1 and name not in function_names
    }
    index.ports = frozenset(
        name for name, facts in index.classes.items() if facts.is_protocol
    )
    return index


def _class_facts(path: Path, node: ast.ClassDef) -> ClassFacts:
    """Reads a class's constructor parameters and whether it is a port."""
    init = next((m for m in methods(node) if m.name == "__init__"), None)
    if init is not None:
        arguments = init.args
        positional = [*arguments.posonlyargs, *arguments.args][1:]
        declared = [*positional, *arguments.kwonlyargs]
        params = tuple(argument.arg for argument in declared)
        annotations = tuple(a.annotation for a in declared if a.annotation)
    elif _is_dataclass(node):
        fields = [
            (member.target.id, member.annotation)
            for member in node.body
            if isinstance(member, ast.AnnAssign)
            and isinstance(member.target, ast.Name)
            and "ClassVar" not in set(_annotation_names(member.annotation))
            and not _is_init_false(member.value)
        ]
        params = tuple(name for name, _ in fields)
        annotations = tuple(note for _, note in fields)
    else:
        params, annotations = (), ()
    return ClassFacts(path, node, params, annotations, _is_protocol(node), init)


def methods(node: ast.ClassDef) -> Iterator[MethodDef]:
    """Yields the methods defined directly in a class body."""
    for member in node.body:
        if isinstance(member, MethodDef):
            yield member


def _annotation_names(note: ast.expr) -> Iterator[str]:
    """Yields each simple name an annotation mentions, quoted ones included."""
    for node in ast.walk(note):
        if isinstance(node, ast.Name):
            yield node.id
        elif isinstance(node, ast.Attribute):
            yield node.attr
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            try:
                parsed = ast.parse(node.value, mode="eval")
            except SyntaxError:
                continue
            yield from _annotation_names(parsed.body)


def _first_party_roots(files: Sequence[tuple[Path, str]]) -> frozenset[str]:
    """Names the top-level packages and modules the package's files form."""
    roots: set[str] = set()
    for path, _ in files:
        top = path.parent if path.name == "__init__.py" else path
        while (top.parent / "__init__.py").exists():
            top = top.parent
        roots.add(top.stem)
    return frozenset(roots)


def _foreign_names(tree: ast.Module, roots: frozenset[str]) -> frozenset[str]:
    """Names a module binds by importing them from outside the package."""
    names: set[str] = set()
    for node in tree.body:
        if (
            isinstance(node, ast.ImportFrom)
            and node.level == 0
            and node.module
            and node.module.split(".")[0] not in roots
        ):
            names |= {alias.asname or alias.name for alias in node.names}
    return frozenset(names)


def _is_dataclass(node: ast.ClassDef) -> bool:
    """Reports whether a class carries a `dataclass` decorator."""
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        name = target.attr if isinstance(target, ast.Attribute) else None
        if isinstance(target, ast.Name):
            name = target.id
        if name == "dataclass":
            return True
    return False


def _is_init_false(value: ast.expr | None) -> bool:
    """Reports whether a dataclass field default is `field(init=False)`."""
    return isinstance(value, ast.Call) and any(
        keyword.arg == "init"
        and isinstance(keyword.value, ast.Constant)
        and keyword.value.value is False
        for keyword in value.keywords
    )


def _is_protocol(node: ast.ClassDef) -> bool:
    """Reports whether a class lists `Protocol` among its bases."""
    for base in node.bases:
        target = base.value if isinstance(base, ast.Subscript) else base
        if isinstance(target, ast.Name) and target.id == "Protocol":
            return True
        if isinstance(target, ast.Attribute) and target.attr == "Protocol":
            return True
    return False
