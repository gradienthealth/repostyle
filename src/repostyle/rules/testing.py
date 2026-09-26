"""Test-suite rules: test naming, the mock ban, and test-quality smells."""

from __future__ import annotations

import ast
import builtins
import re
from collections import Counter, defaultdict
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
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
    RS_REPEATED_TEST_SETUP,
    RS_SHARED_TEST_HELPER,
    RS_SLEEPY_TEST,
    RS_TEST_NAMING,
    RS_TEST_PARAMETRIZATION_CANDIDATE,
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
_BUILTINS = frozenset(dir(builtins))
_DYNAMIC_NAMES = frozenset({"eval", "exec", "globals", "locals", "vars"})
_SCALAR_TYPES = (type(None), bool, int, float, complex, str, bytes)
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
_TEST_REUSE_MINIMUM = 3
_HELPER_STATEMENT_MINIMUM = 3
_TEST_REUSE_PATH_LIMIT = 80


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


@dataclass
class _NormalizationState:
    """Carries name bindings and literal collection through one syntax key."""

    context: _ImportContext
    bindings: dict[str, str]
    should_abstract_literals: bool = False
    is_inside_joined_string: bool = False
    literal_values: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _ParametrizationCandidate:
    """Pairs one test with the scalar values its syntax key abstracted."""

    function: _ReuseFunction
    literal_values: tuple[str, ...]


@dataclass(frozen=True)
class _SetupCandidate:
    """Pairs one test with its leading simple-assignment syntax keys."""

    function: _ReuseFunction
    prefix: tuple[object, ...]
    first_call_assignment: int | None


@dataclass(frozen=True)
class _SetupGroup:
    """Carries one maximal setup prefix and the tests sharing it."""

    assignment_count: int
    members: tuple[_ReuseFunction, ...]
    reported_members: tuple[_ReuseFunction, ...] = ()


@dataclass(frozen=True)
class _SharedHelperCandidate:
    """Carries one helper category, syntax key, and source function."""

    category: str
    key: object
    function: _ReuseFunction


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

    The rule marks tests that may bind a unit to too many collaborators. The
    count prompts review but does not prescribe a change. The rule counts
    `Mock`, `MagicMock`, `patch`, related constructors, and `@patch`
    decorators.
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

    A test whose only checks are `mock.assert_called*` pins collaborator calls
    instead of a caller-visible outcome. A test with at least one plain
    `assert` is left alone, but that exemption does not make the test useful.
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


def check_shared_test_helper(
    files: Sequence[tuple[Path, str]],
) -> Iterator[tuple[Path, Violation]]:
    """Warns about substantial matching helpers across test files.

    Module-level helpers and compatible fixtures qualify after three executable
    statements when their conservative syntax keys match in at least two files.
    The finding marks a candidate for one shared helper or fixture; matching
    syntax does not establish shared lifecycle or semantics.
    """
    groups: dict[object, list[_ReuseFunction]] = defaultdict(list)
    for candidate in _shared_helper_candidates(files):
        groups[(candidate.category, candidate.key)].append(candidate.function)

    for (kind, _), members in groups.items():
        ordered = sorted(
            members, key=lambda item: (item.path.as_posix(), item.node.lineno)
        )
        if len({member.path.resolve() for member in ordered}) < 2:
            continue
        for member in ordered:
            peer = next(item for item in ordered if item.path != member.path)
            message = (
                f"{kind} candidate matches {len(ordered)} definitions across "
                f"test files, including {_display_location(peer)}; consider "
                f"one shared {kind}"
            )
            yield (
                member.path,
                Violation(
                    member.node.lineno,
                    member.node.col_offset + 1,
                    RS_SHARED_TEST_HELPER,
                    message,
                ),
            )


def check_test_parametrization_candidate(
    path: Path, source: str
) -> Iterator[Violation]:
    """Warns when three tests differ only in scalar body literals.

    Candidates stay within one module or class scope and preserve signatures,
    decorators, call targets, operations, and literal types. Existing
    parametrization and syntax with uncertain bindings are left alone.
    """
    if not _is_reuse_test_file(path):
        return
    groups: dict[object, list[_ParametrizationCandidate]] = defaultdict(list)
    for function in _reuse_functions(path, source):
        if not function.node.name.startswith("test_"):
            continue
        if _unsupported_reuse(function) or _is_parametrized(
            function.node, function.context
        ):
            continue
        key, values = _parametrization_key(function)
        groups[key].append(_ParametrizationCandidate(function, values))

    for members in groups.values():
        if len(members) < _TEST_REUSE_MINIMUM:
            continue
        values = [member.literal_values for member in members]
        if not _has_varying_literals(values):
            continue
        for member in members:
            function = member.function
            yield Violation(
                function.node.lineno,
                function.node.col_offset + 1,
                RS_TEST_PARAMETRIZATION_CANDIDATE,
                f"test matches {len(members)} cases that differ only in scalar "
                "body literals; consider `pytest.mark.parametrize` while "
                "retaining distinct contracts",
            )


def check_repeated_test_setup(path: Path, source: str) -> Iterator[Violation]:
    """Warns about repeated leading assignment sequences in tests.

    Three tests in one module or class scope qualify when at least two exact
    leading simple assignments match and the shared prefix includes a call. The
    finding prompts review for a builder or fixture without deciding that the
    call is setup or prescribing fixture lifetime.
    """
    if not _is_reuse_test_file(path):
        return
    by_scope: dict[str, list[_SetupCandidate]] = defaultdict(list)
    for function in _reuse_functions(path, source):
        if not function.node.name.startswith("test_") or _unsupported_reuse(function):
            continue
        prefix, first_call_assignment = _setup_prefix(function)
        if len(prefix) >= 2:
            by_scope[function.scope].append(
                _SetupCandidate(function, prefix, first_call_assignment)
            )

    for scoped in by_scope.values():
        for group in _maximal_setup_groups(scoped):
            for function in group.reported_members:
                yield Violation(
                    function.node.lineno,
                    function.node.col_offset + 1,
                    RS_REPEATED_TEST_SETUP,
                    f"test repeats {group.assignment_count} leading assignments "
                    f"across {len(group.members)} cases; consider a builder or "
                    "fixture",
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


def _reuse_functions(path: Path, source: str) -> list[_ReuseFunction]:
    """Returns directly reviewable functions with their module context."""
    tree = _parse_python(path, source)
    if not isinstance(tree, ast.Module):
        return []
    context = _import_context(tree, path)
    functions: list[_ReuseFunction] = []
    for statement in tree.body:
        if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef):
            functions.append(_ReuseFunction(statement, path, "", context))
        elif isinstance(statement, ast.ClassDef):
            functions.extend(
                _ReuseFunction(member, path, statement.name, context)
                for member in statement.body
                if isinstance(member, ast.FunctionDef | ast.AsyncFunctionDef)
            )
    return functions


def _shared_helper_candidates(
    files: Sequence[tuple[Path, str]],
) -> Iterator[_SharedHelperCandidate]:
    """Yields each eligible helper beside its category and syntax key."""
    for path, source in files:
        if not _is_reuse_test_file(path) or _is_excluded_reuse_file(path):
            continue
        for function in _reuse_functions(path, source):
            candidate = _shared_helper_candidate(function)
            if candidate is not None:
                yield candidate


def _shared_helper_candidate(
    function: _ReuseFunction,
) -> _SharedHelperCandidate | None:
    """Returns an eligible helper candidate, or `None` outside the boundary."""
    if function.scope or function.node.name.startswith("test_"):
        return None
    body = _without_docstring(function.node.body)
    if _unsupported_reuse(function) or len(body) < _HELPER_STATEMENT_MINIMUM:
        return None
    is_fixture = _is_fixture(function.node, function.context)
    return _SharedHelperCandidate(
        "fixture" if is_fixture else "helper",
        _function_key(function, should_preserve_parameter_names=is_fixture),
        function,
    )


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

    def _record(self, name: str) -> None:
        """Records one module binding occurrence."""
        self.names.add(name)
        self.counts[name] += 1

    def visit_Name(self, node: ast.Name) -> None:
        """Records assignment targets."""
        if isinstance(node.ctx, ast.Store | ast.Del):
            self._record(node.id)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Records the definition name without entering its scope."""
        self._record(node.name)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Records the async definition name without entering its scope."""
        self._record(node.name)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Records the class name without entering its scope."""
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


def _raw_imports(tree: ast.Module) -> set[str]:
    """Returns names introduced by direct module imports."""
    return {
        alias.asname or alias.name.split(".", 1)[0]
        for statement in tree.body
        if isinstance(statement, ast.Import | ast.ImportFrom)
        for alias in statement.names
        if alias.name != "*"
    }


def _module_binding_collector(tree: ast.Module) -> _ModuleBindingCollector:
    """Returns bindings introduced outside direct module imports."""
    collector = _ModuleBindingCollector()
    for statement in tree.body:
        if not isinstance(statement, ast.Import | ast.ImportFrom):
            collector.visit(statement)
    return collector


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


def _module_bindings(tree: ast.Module) -> set[str]:
    """Returns every name bound directly in a module."""
    return _raw_imports(tree) | _module_binding_collector(tree).names


def _has_wildcard_import(tree: ast.Module) -> bool:
    """Reports whether module execution can bind names through `import *`."""
    direct = any(
        isinstance(statement, ast.ImportFrom)
        and any(alias.name == "*" for alias in statement.names)
        for statement in tree.body
    )
    return direct or _module_binding_collector(tree).has_wildcard_import


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


class _BindingCollector(ast.NodeVisitor):
    """Collects function-local names in source traversal order."""

    def __init__(self, bindings: dict[str, str]) -> None:
        self.bindings = bindings

    def visit_Name(self, node: ast.Name) -> None:
        """Records a stored name once."""
        if isinstance(node.ctx, ast.Store | ast.Del) and node.id not in self.bindings:
            self.bindings[node.id] = f"local:{len(self.bindings)}"

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        """Records an exception target before visiting its body."""
        if node.name and node.name not in self.bindings:
            self.bindings[node.name] = f"local:{len(self.bindings)}"
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Stops at a nested scope."""

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Stops at a nested async scope."""

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Stops at a nested class scope."""


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


def _without_docstring(statements: list[ast.stmt]) -> list[ast.stmt]:
    """Returns body statements after an optional leading docstring."""
    if statements and isinstance(statements[0], ast.Expr):
        value = statements[0].value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return statements[1:]
    return statements


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


def _decorator_tail(node: ast.expr) -> str:
    """Returns the final syntactic name of a decorator expression."""
    expression = node.func if isinstance(node, ast.Call) else node
    if isinstance(expression, ast.Name):
        return expression.id
    if isinstance(expression, ast.Attribute):
        return expression.attr
    return ""


def _decorator_name(node: ast.expr, context: _ImportContext) -> str:
    """Returns a straightforward qualified expression identity."""
    expression = node.func if isinstance(node, ast.Call) else node
    if isinstance(expression, ast.Name):
        return context.external_name(expression.id)[1]
    if isinstance(expression, ast.Attribute):
        base = _decorator_name(expression.value, context)
        return f"{base}.{expression.attr}" if base else expression.attr
    return ""


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


def _has_varying_literals(values: list[tuple[str, ...]]) -> bool:
    """Reports an aligned literal position with differing values."""
    return (
        bool(values)
        and len({len(items) for items in values}) == 1
        and any(
            len({items[index] for items in values}) > 1
            for index in range(len(values[0]))
        )
    )


def _setup_prefix(function: _ReuseFunction) -> tuple[tuple[object, ...], int | None]:
    """Returns leading assignment keys and the first call-bearing value."""
    bindings = _function_bindings(function.node, should_preserve_parameter_names=True)
    state = _NormalizationState(function.context, bindings)
    prefix: list[object] = []
    first_call_assignment: int | None = None
    for statement in _without_docstring(function.node.body):
        if isinstance(statement, ast.Assign):
            if len(statement.targets) != 1 or not isinstance(
                statement.targets[0], ast.Name
            ):
                break
            value = statement.value
        elif isinstance(statement, ast.AnnAssign):
            if not isinstance(statement.target, ast.Name) or statement.value is None:
                break
            value = statement.value
        else:
            break
        prefix.append(_node_key(statement, state))
        if first_call_assignment is None and any(
            isinstance(child, ast.Call) for child in ast.walk(value)
        ):
            first_call_assignment = len(prefix)
    return tuple(prefix), first_call_assignment


def _maximal_setup_groups(
    scoped: list[_SetupCandidate],
) -> list[_SetupGroup]:
    """Returns the longest qualifying prefix for each matching member group."""
    prefix_groups: dict[object, list[_ReuseFunction]] = defaultdict(list)
    for item in scoped:
        for length in range(2, len(item.prefix) + 1):
            candidate = item.prefix[:length]
            if (
                item.first_call_assignment is not None
                and item.first_call_assignment <= length
            ):
                prefix_groups[candidate].append(item.function)
    best: dict[tuple[str, ...], _SetupGroup] = {}
    for prefix, members in prefix_groups.items():
        unique = sorted(
            {member.qualified_name: member for member in members}.values(),
            key=lambda item: item.node.lineno,
        )
        if len(unique) < _TEST_REUSE_MINIMUM:
            continue
        member_key = tuple(member.qualified_name for member in unique)
        group = _SetupGroup(len(prefix), tuple(unique))
        if len(prefix) > best.get(member_key, _SetupGroup(0, ())).assignment_count:
            best[member_key] = group
    claimed: set[str] = set()
    selected: list[_SetupGroup] = []
    for group in sorted(
        best.values(),
        key=lambda item: (
            -item.assignment_count,
            -len(item.members),
            tuple(member.qualified_name for member in item.members),
        ),
    ):
        reported = tuple(
            member for member in group.members if member.qualified_name not in claimed
        )
        if not reported:
            continue
        claimed.update(member.qualified_name for member in reported)
        selected.append(_SetupGroup(group.assignment_count, group.members, reported))
    return selected


def _is_reuse_test_file(path: Path) -> bool:
    """Reports whether `path` can define a test or test support code."""
    return path.suffix == ".py" and _is_test_file(path)


def _is_excluded_reuse_file(path: Path) -> bool:
    """Reports whether config excludes `path` from findings."""
    pyproject = find_pyproject(path)
    return _matches_config_glob(path, pyproject, _repostyle_table(pyproject), "exclude")


def _display_location(function: _ReuseFunction) -> str:
    """Returns a repository-relative peer location."""
    pyproject = find_pyproject(function.path)
    try:
        displayed = function.path.relative_to(pyproject.parent) if pyproject else None
    except ValueError:
        displayed = None
    path = (displayed or function.path).as_posix()
    if len(path) > _TEST_REUSE_PATH_LIMIT:
        path = f"…{path[-(_TEST_REUSE_PATH_LIMIT - 1) :]}"
    return f"{path}:{function.node.lineno}"
