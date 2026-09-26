"""Internal implementation partition 2."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from repostyle._shared import (
    _has_decorator,
    _is_test_file,
    _parse_python,
    _walk_tree,
    find_pyproject,
)
from repostyle.rules._testing_impl_3 import (
    internal_module_helpers,
    internal_parse_conftest,
    internal_pins_literals,
    internal_quantifies,
)
from repostyle.rules._testing_impl_4 import (
    InternalTestFunction,
    internal_reached_names,
    internal_referenced_names,
    internal_scoped_functions,
)
from repostyle.rules._violation import (
    RS_FILE_LITERAL_RESTATEMENT,
    Violation,
)


def check_file_literal_restatement(path: Path, source: str) -> Iterator[Violation]:
    """Warns when a test only quotes back literals from one repo file.

    A test that parses a single file, compares what it finds to literals, and
    exercises nothing beyond the parser restates that file: one edit changes
    the assertion and the value together, and no rewrite preserving the
    behavior a caller relies on can break it. Three shapes are left alone, each
    pinning something a single edit can still break -- a test reaching two or
    more files, one comparing a value it derived to another derived value, and
    one asserting a property across every entry it read.
    """
    if not _is_test_file(path):
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    scope = _resolved_scope(path, tree)
    for owner, function in _classified_test_functions(tree):
        names = internal_reached_names(function, owner, scope.fixtures, scope.helpers)
        if (
            names is None
            or _exercises_code(names, scope)
            or internal_quantifies(function)
        ):
            continue
        restated = sorted(names & scope.constants)
        if len(restated) != 1 or not internal_pins_literals(function):
            continue
        yield Violation(
            function.lineno,
            function.col_offset + 1,
            RS_FILE_LITERAL_RESTATEMENT,
            f"test '{function.name}' asserts only literals it read through `{restated[0]}`; assert the property where it executes, or pin it against the second file that has to agree",
        )


def internal_branch_asserts_directly(node: ast.stmt) -> bool:
    """Reports whether a branch or loop statement asserts in its own body."""
    bodies: list[list[ast.stmt]] = [node.body, getattr(node, "orelse", [])]
    if isinstance(node, ast.Try):
        bodies.append(node.finalbody)
        bodies.extend(handler.body for handler in node.handlers)
    return any(isinstance(stmt, ast.Assert) for body in bodies for stmt in body)


def _classified_test_functions(
    tree: ast.AST,
) -> Iterator[tuple[str, InternalTestFunction]]:
    """Yields each test function beside the name of the class holding it.

    A function defined outside a class takes the empty string, which is the key
    its module-level fixtures are stored under.
    """
    for owner, function in internal_scoped_functions(tree):
        if function.name.startswith("test_"):
            yield (owner, function)


def _resolved_scope(path: Path, tree: ast.AST) -> _ResolvedScope:
    """Merges a test module's own scope with every `conftest.py` above it.

    A nearer definition shadows a farther one, matching how pytest resolves a
    fixture, so the module's own names win over the closest `conftest.py` and
    that one wins over its parents.
    """
    trees = [tree, *_conftest_trees(path)]
    fixtures: dict[tuple[str, str], InternalTestFunction] = {}
    helpers: dict[str, InternalTestFunction] = {}
    constants: set[str] = set()
    for module in reversed(trees):
        fixtures.update(_fixture_scopes(module))
        helpers.update(internal_module_helpers(module))
        constants |= _file_constants(module)
    return _ResolvedScope(fixtures, helpers, constants, tuple(trees))


def _conftest_trees(path: Path) -> list[ast.AST]:
    """Parses each `conftest.py` from a test's directory up to the root.

    The nearest one comes first. A directory holding no readable `conftest.py`
    contributes nothing, which leaves a test whose fixtures live outside the
    project unresolved rather than guessed at.
    """
    pyproject = find_pyproject(path)
    root = pyproject.parent if pyproject is not None else None
    trees: list[ast.AST] = []
    directory = path.parent
    while True:
        conftest = directory / "conftest.py"
        parsed = internal_parse_conftest(conftest) if conftest != path else None
        if parsed is not None:
            trees.append(parsed)
        if directory == root or directory == directory.parent:
            return trees
        directory = directory.parent


def _exercises_code(names: set[str], scope: _ResolvedScope) -> bool:
    """Reports whether a test reaches past parsing the file it read.

    A name bound by an import outside the parser vocabulary is the unit under
    test, and a name reading file metadata asserts something the file's own
    text does not state. Every module in scope is searched, since a fixture a
    `conftest.py` supplies is built from that module's imports.
    """
    if names & FILE_METADATA_NAMES:
        return True
    return any(
        (
            bound in names
            for tree in scope.trees
            for node in _walk_tree(tree)
            for root, bound in _import_bindings(node)
            if root not in FILE_PARSER_MODULES
        )
    )


FILE_PARSER_MODULES = frozenset(
    {
        "collections",
        "configparser",
        "json",
        "pathlib",
        "pytest",
        "re",
        "tomllib",
        "typing",
        "yaml",
    }
)

FILE_METADATA_NAMES = frozenset({"access", "lstat", "st_mode", "stat"})


@dataclass(frozen=True)
class _ResolvedScope:
    """Everything a test module can reach, its `conftest.py` chain included."""

    fixtures: dict[tuple[str, str], InternalTestFunction]
    "Each fixture keyed by the class holding it and its own name."
    helpers: dict[str, InternalTestFunction]
    "The module-level functions that are not themselves tests."
    constants: set[str]
    "The names bound to a repo file."
    trees: tuple[ast.AST, ...]
    "The test module and each `conftest.py` above it, nearest first."


def _file_constants(tree: ast.AST) -> set[str]:
    """Returns the module-level names bound to a repo file.

    A name assigned a `Path` expression seeds the set, and one assigned from a
    name already in it joins, so a constant built by joining onto a resolved
    repository root counts as the file it names.
    """
    assignments = [
        node for node in getattr(tree, "body", []) if isinstance(node, ast.Assign)
    ]
    names: set[str] = set()
    bound = -1
    while bound != len(names):
        bound = len(names)
        for node in assignments:
            if _binds_repo_file(node, names):
                names |= {
                    target.id for target in node.targets if isinstance(target, ast.Name)
                }
    return names


def _binds_repo_file(node: ast.Assign, known: set[str]) -> bool:
    """Reports whether an assignment binds a name to a repo file.

    A `Path` expression binds one outright; so does an expression joining onto
    a name already known to hold one, which is how a constant built from a
    resolved repository root reads. The reference has to be to the name `Path`
    itself, so a constant whose value is the string `Path` binds nothing.
    """
    referenced = internal_referenced_names(node.value)
    return "Path" in referenced or bool(referenced & known)


def _fixture_scopes(tree: ast.AST) -> dict[tuple[str, str], InternalTestFunction]:
    """Returns each fixture keyed by the class holding it and its own name.

    A module-level fixture takes the empty string as its class, so a lookup
    falls back to it when the requesting class defines no fixture of that name.
    """
    return {
        (owner, function.name): function
        for owner, function in internal_scoped_functions(tree)
        if _has_decorator(function, _FIXTURE_DECORATORS)
    }


_FIXTURE_DECORATORS = frozenset({"fixture"})


def _import_bindings(node: ast.AST) -> Iterator[tuple[str, str]]:
    """Yields the root module and bound name of each import a node makes."""
    if isinstance(node, ast.ImportFrom):
        root = (node.module or "").split(".")[0]
        for alias in node.names:
            yield (root, alias.asname or alias.name)
    elif isinstance(node, ast.Import):
        for alias in node.names:
            root = alias.name.split(".")[0]
            yield (root, alias.asname or root)
