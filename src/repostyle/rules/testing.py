"""Test-suite rules: test naming, the mock ban, and test-quality smells."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from repostyle._shared import (
    _has_decorator,
    _is_test_file,
    _matches_config_glob,
    _parse_python,
    _posix,
    _repostyle_table,
    _string_list,
    _walk_tree,
    find_pyproject,
)
from repostyle.rules._violation import (
    RS_BEHAVIOR_VERIFICATION_ONLY,
    RS_CONDITIONAL_TEST_LOGIC,
    RS_EXCESSIVE_MOCKING,
    RS_FILE_LITERAL_RESTATEMENT,
    RS_NO_MOCK_PATCH,
    RS_SLEEPY_TEST,
    RS_TEST_NAMING,
    Violation,
)

TEST_NAME_PATTERN = re.compile(r"^test_[A-Z][A-Za-z0-9]*_[A-Z][A-Za-z0-9]*$")
FAKES_PATH_FRAGMENT = "tests/fakes/"
UNIT_TEST_PATH_FRAGMENT = "tests/unit/"
TEST_NAMING_GLOBS_KEY = "test-naming-globs"
SLEEP_MODULES = frozenset({"time", "asyncio"})
MOCK_CONSTRUCTORS = frozenset(
    {"Mock", "MagicMock", "AsyncMock", "NonCallableMock", "patch"}
)
FORBIDDEN_MOCK_MODULES = frozenset({"unittest.mock", "mock"})
EXCESSIVE_MOCK_LIMIT = 3
# What a test may reach and still be reading a file rather than exercising
# code: the parsers, the path and typing vocabulary the reading needs, and
# pytest itself. An import outside this set is the unit under test.
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
# Metadata a diff cannot show, so a test asserting it is not restating the
# file's own text.
FILE_METADATA_NAMES = frozenset({"access", "lstat", "st_mode", "stat"})
# Built-in pytest fixtures that supply a temporary directory, a capture, or a
# patcher, never a repo file or a unit under test. A test requesting one is
# still fully resolved, unlike `request` or a mock factory, which can supply
# anything and leave the test unanalyzable.
INERT_PYTEST_FIXTURES = frozenset(
    {
        "capfd",
        "capfdbinary",
        "caplog",
        "capsys",
        "capsysbinary",
        "monkeypatch",
        "recwarn",
        "tmp_path",
        "tmp_path_factory",
        "tmpdir",
        "tmpdir_factory",
    }
)
# Constructors that leave a literal argument a literal, so a collection built
# from one still states its own value.
LITERAL_COLLECTION_BUILTINS = frozenset({"frozenset", "list", "set", "sorted", "tuple"})
_BRANCH_STATEMENTS = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try)
_FIXTURE_DECORATORS = frozenset({"fixture"})
_QUANTIFIERS = (
    ast.AsyncFor,
    ast.DictComp,
    ast.For,
    ast.GeneratorExp,
    ast.ListComp,
    ast.SetComp,
)
_SELF_ARGUMENTS = frozenset({"cls", "self"})
_TestFunction = ast.AsyncFunctionDef | ast.FunctionDef


@dataclass(frozen=True)
class _ResolvedScope:
    """Everything a test module can reach, its `conftest.py` chain included."""

    fixtures: dict[tuple[str, str], _TestFunction]
    """Each fixture keyed by the class holding it and its own name."""
    helpers: dict[str, _TestFunction]
    """The module-level functions that are not themselves tests."""
    constants: set[str]
    """The names bound to a repo file."""
    trees: tuple[ast.AST, ...]
    """The test module and each `conftest.py` above it, nearest first."""


def check_test_naming(path: Path, source: str) -> Iterator[Violation]:
    """A unit test matches `test_StateUnderTest_ExpectedBehavior`.

    Applies to files under `tests/unit/`, or, when the config sets
    `test-naming-globs`, to the files matching those globs instead, so a repo
    keeping its unit tests elsewhere can still hold them to the naming.
    `conftest.py` and `__init__.py` are exempt in either scope.
    """
    if not _is_in_test_naming_scope(path):
        return
    if path.name in {"conftest.py", "__init__.py"}:
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in _walk_tree(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if not node.name.startswith("test_"):
            continue
        if TEST_NAME_PATTERN.match(node.name):
            continue
        yield Violation(
            node.lineno,
            node.col_offset + 1,
            RS_TEST_NAMING,
            f"test '{node.name}' must match `test_StateUnderTest_ExpectedBehavior`",
        )


def check_no_mock_patch(path: Path, source: str) -> Iterator[Violation]:
    """`unittest.mock` and `mock` imports are rejected outside tests/fakes/."""
    if FAKES_PATH_FRAGMENT in _posix(path):
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in _walk_tree(tree):
        offending = _offending_mock_import(node)
        if offending is None:
            continue
        yield Violation(
            node.lineno,
            node.col_offset + 1,
            RS_NO_MOCK_PATCH,
            f"`{offending}` rejected; use a port fake under tests/fakes/",
        )


def check_conditional_test_logic(path: Path, source: str) -> Iterator[Violation]:
    """A test may not wrap an `assert` in conditional or loop logic.

    An `if`, `for`, `while`, or `try` whose own body asserts makes the asserted
    path depend on runtime state, so a test that never enters the branch passes
    vacuously. Keep test bodies straight-line, or split the cases into separate
    tests or parametrized rows.
    """
    if not _is_test_file(path):
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    for function in _test_functions(tree):
        for node in ast.walk(function):
            if isinstance(node, _BRANCH_STATEMENTS) and _branch_asserts_directly(node):
                yield Violation(
                    node.lineno,
                    node.col_offset + 1,
                    RS_CONDITIONAL_TEST_LOGIC,
                    f"test '{function.name}' wraps an `assert` in control flow; "
                    f"keep the asserted path straight-line",
                )


def check_sleepy_test(path: Path, source: str) -> Iterator[Violation]:
    """A test may not call `time.sleep` or `asyncio.sleep`.

    A real sleep makes the suite slow and couples it to wall-clock timing, the
    usual source of flakes; wait on the observable condition or drive a fake
    clock instead. A literal `sleep(0)` is exempt: it is the idiomatic
    single-turn yield to the event loop, neither slow nor flaky.
    """
    if not _is_test_file(path):
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    for function in _test_functions(tree):
        for node in ast.walk(function):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "sleep"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in SLEEP_MODULES
                and not _is_zero_sleep(node)
            ):
                yield Violation(
                    node.lineno,
                    node.col_offset + 1,
                    RS_SLEEPY_TEST,
                    f"`{node.func.value.id}.sleep(...)` in a test is slow and "
                    f"flaky; wait on a condition or use a fake clock",
                )


def check_excessive_mocking(path: Path, source: str) -> Iterator[Violation]:
    """Warns when a test builds many mock objects.

    A high mock count per test points at over-mocked, brittle coupling worth a
    look; it is a density signal of where to look, not a verdict that any
    single mock is wrong. Counts `Mock`/`MagicMock`/`patch` and their kin,
    including `@patch` decorators.
    """
    if not _is_test_file(path):
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    for function in _test_functions(tree):
        count = sum(
            1 for decorator in function.decorator_list if _is_mock_decorator(decorator)
        )
        for statement in function.body:
            for node in ast.walk(statement):
                if isinstance(node, ast.Call) and _mock_construct_name(node.func):
                    count += 1
        if count > EXCESSIVE_MOCK_LIMIT:
            yield Violation(
                function.lineno,
                function.col_offset + 1,
                RS_EXCESSIVE_MOCKING,
                f"test '{function.name}' builds {count} mocks; over "
                f"{EXCESSIVE_MOCK_LIMIT} marks where to look, not that any one "
                f"mock is wrong",
            )


def check_behavior_verification_only(path: Path, source: str) -> Iterator[Violation]:
    """Warns when a test asserts only call choreography, never state.

    A test whose only checks are `mock.assert_called*` pins how the unit calls
    its collaborators rather than the outcome a caller relies on, so it
    survives a correct refactor and breaks on a harmless one. A test with at
    least one plain `assert` is left alone.
    """
    if not _is_test_file(path):
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    for function in _test_functions(tree):
        nodes = [node for statement in function.body for node in ast.walk(statement)]
        asserts_state = any(isinstance(node, ast.Assert) for node in nodes)
        asserts_calls = any(_is_choreography_call(node) for node in nodes)
        if asserts_calls and not asserts_state:
            yield Violation(
                function.lineno,
                function.col_offset + 1,
                RS_BEHAVIOR_VERIFICATION_ONLY,
                f"test '{function.name}' asserts only call choreography, not "
                f"observable state",
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
        names = _reached_names(function, owner, scope.fixtures, scope.helpers)
        if names is None or _exercises_code(names, scope) or _quantifies(function):
            continue
        restated = sorted(names & scope.constants)
        if len(restated) != 1 or not _pins_literals(function):
            continue
        yield Violation(
            function.lineno,
            function.col_offset + 1,
            RS_FILE_LITERAL_RESTATEMENT,
            f"test '{function.name}' asserts only literals it read through "
            f"`{restated[0]}`; assert the property where it executes, or pin "
            f"it against the second file that has to agree",
        )


def _branch_asserts_directly(node: ast.stmt) -> bool:
    """Reports whether a branch or loop statement asserts in its own body."""
    bodies: list[list[ast.stmt]] = [node.body, getattr(node, "orelse", [])]
    if isinstance(node, ast.Try):
        bodies.append(node.finalbody)
        bodies.extend(handler.body for handler in node.handlers)
    return any(isinstance(stmt, ast.Assert) for body in bodies for stmt in body)


def _classified_test_functions(tree: ast.AST) -> Iterator[tuple[str, _TestFunction]]:
    """Yields each test function beside the name of the class holding it.

    A function defined outside a class takes the empty string, which is the key
    its module-level fixtures are stored under.
    """
    for owner, function in _scoped_functions(tree):
        if function.name.startswith("test_"):
            yield owner, function


def _resolved_scope(path: Path, tree: ast.AST) -> _ResolvedScope:
    """Merges a test module's own scope with every `conftest.py` above it.

    A nearer definition shadows a farther one, matching how pytest resolves a
    fixture, so the module's own names win over the closest `conftest.py` and
    that one wins over its parents.
    """
    trees = [tree, *_conftest_trees(path)]
    fixtures: dict[tuple[str, str], _TestFunction] = {}
    helpers: dict[str, _TestFunction] = {}
    constants: set[str] = set()
    for module in reversed(trees):
        fixtures.update(_fixture_scopes(module))
        helpers.update(_module_helpers(module))
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
        parsed = _parse_conftest(conftest) if conftest != path else None
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
        bound in names
        for tree in scope.trees
        for node in _walk_tree(tree)
        for root, bound in _import_bindings(node)
        if root not in FILE_PARSER_MODULES
    )


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
    referenced = _referenced_names(node.value)
    return "Path" in referenced or bool(referenced & known)


def _fixture_scopes(tree: ast.AST) -> dict[tuple[str, str], _TestFunction]:
    """Returns each fixture keyed by the class holding it and its own name.

    A module-level fixture takes the empty string as its class, so a lookup
    falls back to it when the requesting class defines no fixture of that name.
    """
    return {
        (owner, function.name): function
        for owner, function in _scoped_functions(tree)
        if _has_decorator(function, _FIXTURE_DECORATORS)
    }


def _import_bindings(node: ast.AST) -> Iterator[tuple[str, str]]:
    """Yields the root module and bound name of each import a node makes."""
    if isinstance(node, ast.ImportFrom):
        root = (node.module or "").split(".")[0]
        for alias in node.names:
            yield root, alias.asname or alias.name
    elif isinstance(node, ast.Import):
        for alias in node.names:
            root = alias.name.split(".")[0]
            yield root, alias.asname or root


def _is_choreography_call(node: ast.AST) -> bool:
    """Reports whether a node is a `mock.assert_called*`-style call."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and (
            node.func.attr.startswith("assert_called")
            or node.func.attr
            in {"assert_has_calls", "assert_not_called", "assert_any_call"}
        )
    )


def _is_in_test_naming_scope(path: Path) -> bool:
    """Reports whether `path` falls in RS002's naming scope.

    The `test-naming-globs` config, when set, replaces the default
    `tests/unit/` path fragment rather than extending it, so a repo states its
    whole test layout in one place.
    """
    pyproject = find_pyproject(path)
    table = _repostyle_table(pyproject)
    if _string_list(table, TEST_NAMING_GLOBS_KEY):
        return _matches_config_glob(path, pyproject, table, TEST_NAMING_GLOBS_KEY)
    return UNIT_TEST_PATH_FRAGMENT in _posix(path)


@cache
def _parse_conftest(conftest: Path) -> ast.AST | None:
    """Parses a `conftest.py`, or returns `None` when it cannot be read.

    Cached because every test module under a directory resolves through the
    same file, and a lint run reads one snapshot of the tree.
    """
    try:
        source = conftest.read_text(encoding="utf-8")
    except OSError:
        return None
    return _parse_python(conftest, source)


def _pins_literals(function: _TestFunction) -> bool:
    """Reports whether every comparison a test asserts faces a literal.

    A test qualifies when it asserts at least one comparison and none of them
    weighs one derived value against another, since such a comparison holds two
    places to one agreement rather than restating a single one.
    """
    comparisons = [
        node.test
        for node in ast.walk(function)
        if isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare)
    ]
    return bool(comparisons) and all(
        any(_is_literal(side) for side in (test.left, *test.comparators))
        or all(_restates_content(side) for side in (test.left, *test.comparators))
        for test in comparisons
    )


def _is_literal(node: ast.AST) -> bool:
    """Reports whether an expression is a literal the source states outright.

    A constant, a negated constant, a collection whose entries are all
    literals, and a bare conversion of one all qualify; anything read from a
    parsed structure does not.
    """
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.UnaryOp):
        return _is_literal(node.operand)
    if isinstance(node, ast.List | ast.Set | ast.Tuple):
        return all(_is_literal(element) for element in node.elts)
    if isinstance(node, ast.Dict):
        keys = [key for key in node.keys if key is not None]
        return all(_is_literal(entry) for entry in (*keys, *node.values))
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in LITERAL_COLLECTION_BUILTINS
    ):
        return all(_is_literal(argument) for argument in node.args)
    return False


def _is_mock_decorator(decorator: ast.expr) -> bool:
    """Reports whether a decorator constructs or patches with a mock."""
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    return _mock_construct_name(target) is not None


def _is_zero_sleep(node: ast.Call) -> bool:
    """Reports whether a sleep call's delay is a literal zero."""
    if not node.args:
        return False
    delay = node.args[0]
    return (
        isinstance(delay, ast.Constant)
        and isinstance(delay.value, int | float)
        and not isinstance(delay.value, bool)
        and delay.value == 0
    )


def _mock_construct_name(func: ast.expr) -> str | None:
    """Returns the mock constructor a call target names, or `None`."""
    if isinstance(func, ast.Name):
        return func.id if func.id in MOCK_CONSTRUCTORS else None
    if isinstance(func, ast.Attribute):
        if func.attr in MOCK_CONSTRUCTORS:
            return func.attr
        if isinstance(func.value, ast.Name) and func.value.id in MOCK_CONSTRUCTORS:
            return func.value.id
    return None


def _module_helpers(tree: ast.AST) -> dict[str, _TestFunction]:
    """Returns the module-level functions that are not themselves tests."""
    return {
        node.name: node
        for node in getattr(tree, "body", [])
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and not node.name.startswith("test_")
    }


def _offending_mock_import(node: ast.AST) -> str | None:
    """Returns the rendered forbidden mock import a node makes, or `None`."""
    if isinstance(node, ast.Import):
        return _offending_plain_import(node)
    if isinstance(node, ast.ImportFrom):
        return _offending_from_import(node)
    return None


def _offending_from_import(node: ast.ImportFrom) -> str | None:
    """Returns the rendered forbidden `from` import a node makes, or `None`."""
    if node.module in FORBIDDEN_MOCK_MODULES:
        return f"from {node.module} import ..."
    if node.module == "unittest" and any(alias.name == "mock" for alias in node.names):
        return "from unittest import mock"
    return None


def _offending_plain_import(node: ast.Import) -> str | None:
    """Returns the rendered forbidden plain import a node makes, or `None`."""
    for alias in node.names:
        root = alias.name.split(".", 1)[0]
        if alias.name in FORBIDDEN_MOCK_MODULES or root == "mock":
            return f"import {alias.name}"
    return None


def _quantifies(function: _TestFunction) -> bool:
    """Reports whether a test asserts across every entry it read.

    A comprehension or loop in the test's own body states a property that holds
    for each entry, which an edit adding an entry can still break, so it is not
    a restatement of what the file happens to say today.
    """
    return any(isinstance(node, _QUANTIFIERS) for node in ast.walk(function))


def _reached_names(
    function: _TestFunction,
    owner: str,
    scopes: dict[tuple[str, str], _TestFunction],
    helpers: dict[str, _TestFunction],
    seen: set[str] | None = None,
    *,
    should_resolve_fixtures: bool = True,
) -> set[str] | None:
    """Returns every name a test reaches through its fixtures and helpers.

    Resolution is `None` when any fixture on the path is undefined in this
    module, since what it supplies cannot be known from this file alone. A
    module helper is expanded by name only: its parameters are ordinary
    arguments its callers pass, not fixtures pytest resolves.
    """
    seen = set() if seen is None else seen
    names = _referenced_names(function)
    for name in sorted(names & helpers.keys() - seen):
        seen.add(name)
        reached = _reached_names(
            helpers[name], owner, scopes, helpers, seen, should_resolve_fixtures=False
        )
        if reached is None:
            return None
        names |= reached
    if not should_resolve_fixtures:
        return names
    requested = _requested_fixtures(function, owner, scopes)
    if requested is None:
        return None
    for fixture in requested:
        if fixture.name in seen:
            continue
        seen.add(fixture.name)
        reached = _reached_names(fixture, owner, scopes, helpers, seen)
        if reached is None:
            return None
        names |= reached
    return names


def _referenced_names(node: ast.AST) -> set[str]:
    """Returns the names and attributes an expression or body references."""
    names: set[str] = set()
    for inner in ast.walk(node):
        if isinstance(inner, ast.Name):
            names.add(inner.id)
        elif isinstance(inner, ast.Attribute):
            names.add(inner.attr)
    return names


def _requested_fixtures(
    function: _TestFunction,
    owner: str,
    scopes: dict[tuple[str, str], _TestFunction],
) -> list[_TestFunction] | None:
    """Returns the fixtures a definition requests, or `None` if one is foreign.

    A parameter resolves against the holding class first and the module next,
    matching how pytest shadows a fixture; one that neither scope defines comes
    from `conftest.py` or from pytest itself and can supply anything.
    """
    arguments = function.args
    requested: list[_TestFunction] = []
    for argument in (
        *arguments.posonlyargs,
        *arguments.args,
        *arguments.kwonlyargs,
    ):
        if argument.arg in _SELF_ARGUMENTS or argument.arg in INERT_PYTEST_FIXTURES:
            continue
        fixture = scopes.get((owner, argument.arg)) or scopes.get(("", argument.arg))
        if fixture is None:
            return None
        requested.append(fixture)
    return requested


def _restates_content(operand: ast.expr) -> bool:
    """Reports whether an operand carries a string the parsed file supplied.

    A string indexing into the structure names where to look, so it is
    excluded; a string anywhere else in the operand is the file's own content
    quoted back, which is what an ordering or membership check compares.
    """
    keys = _subscript_key_ids(operand)
    return any(
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in keys
        for node in ast.walk(operand)
    )


def _scoped_functions(tree: ast.AST) -> Iterator[tuple[str, _TestFunction]]:
    """Yields every function beside the name of the class that holds it.

    A function defined at module level takes the empty string, so the two
    scopes pytest resolves a fixture through share one key space.
    """
    for node in _walk_tree(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for member in node.body:
            if isinstance(member, ast.FunctionDef | ast.AsyncFunctionDef):
                yield node.name, member
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            yield "", node


def _subscript_key_ids(node: ast.AST) -> set[int]:
    """Returns the identities of the constants used as subscript keys."""
    return {
        id(inner)
        for outer in ast.walk(node)
        if isinstance(outer, ast.Subscript)
        for inner in ast.walk(outer.slice)
        if isinstance(inner, ast.Constant)
    }


def _test_functions(
    tree: ast.AST,
) -> Iterator[ast.AsyncFunctionDef | ast.FunctionDef]:
    """Yields the `test`-prefixed functions and methods defined in the tree."""
    for node in _walk_tree(tree):
        if isinstance(
            node, ast.FunctionDef | ast.AsyncFunctionDef
        ) and node.name.startswith("test"):
            yield node
