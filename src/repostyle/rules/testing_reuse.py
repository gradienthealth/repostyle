"""Test-suite reuse rules for helpers, parametrization, and setup."""

from __future__ import annotations

import ast
import itertools
import re
from collections import defaultdict
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from repostyle._shared import (
    _is_test_file,
    _matches_config_glob,
    _parse_python,
    _repostyle_table,
    find_pyproject,
)
from repostyle.rules._test_reuse_context import (
    _import_context,
    _is_fixture,
    _is_parametrized,
    _ReuseFunction,
    _unsupported_reuse,
)
from repostyle.rules._test_reuse_keys import (
    _function_key,
    _parametrization_key,
    _setup_prefix,
    _without_docstring,
)
from repostyle.rules._violation import (
    RS_REPEATED_TEST_SETUP,
    RS_SHARED_TEST_HELPER,
    RS_TEST_PARAMETRIZATION_CANDIDATE,
    Violation,
)

_TEST_REUSE_MINIMUM = 3
_HELPER_STATEMENT_MINIMUM = 3
_TEST_REUSE_PATH_LIMIT = 80
_TEST_NAME_TERM = re.compile(r"[A-Z]+(?=[A-Z][a-z]|\b)|[A-Z]?[a-z]+|\d+")
_GENERIC_TEST_NAME_TERMS = frozenset(
    {"checked", "flags", "no", "not", "nothing", "reports", "violation"}
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
    """Finds scalar test cases that form one named contract.

    A candidate contains at least three tests in one module or class. Its tests
    share two meaningful name words and the same supported syntax after scalar
    values are abstracted. Signatures, decorators, operations, call targets,
    literal types, and multi-line fixture programs remain distinct. The check
    skips existing parametrization and bindings it cannot resolve safely.
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

    for structurally_matching in groups.values():
        for members in _contract_groups(structurally_matching):
            yield from _parametrization_findings(members)


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


def _contract_groups(
    members: list[_ParametrizationCandidate],
) -> list[list[_ParametrizationCandidate]]:
    """Returns maximal groups that share a two-term contract stem."""
    by_term_pair: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, member in enumerate(members):
        terms = sorted(_test_name_terms(member.function.node.name))
        for pair in itertools.combinations(terms, 2):
            by_term_pair[pair].append(index)

    qualifying = {
        frozenset(group)
        for group in by_term_pair.values()
        if len(group) >= _TEST_REUSE_MINIMUM
    }
    maximal = [
        group for group in qualifying if not any(group < other for other in qualifying)
    ]
    claimed: set[int] = set()
    selected: list[list[_ParametrizationCandidate]] = []
    for group in sorted(
        maximal,
        key=lambda candidate: (
            -len(candidate),
            min(members[index].function.node.lineno for index in candidate),
        ),
    ):
        unclaimed = sorted(
            group - claimed, key=lambda index: members[index].function.node.lineno
        )
        if len(unclaimed) < _TEST_REUSE_MINIMUM:
            continue
        claimed.update(unclaimed)
        selected.append([members[index] for index in unclaimed])
    return selected


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


def _parametrization_findings(
    members: list[_ParametrizationCandidate],
) -> Iterator[Violation]:
    """Yields findings for one contract-coherent candidate group."""
    values = [member.literal_values for member in members]
    if not _has_varying_literals(values):
        return
    for member in members:
        function = member.function
        yield Violation(
            function.node.lineno,
            function.node.col_offset + 1,
            RS_TEST_PARAMETRIZATION_CANDIDATE,
            f"test matches {len(members)} cases that differ only in scalar "
            "body literals; consider `pytest.mark.parametrize` while retaining "
            "distinct contracts",
        )


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


def _is_excluded_reuse_file(path: Path) -> bool:
    """Reports whether config excludes `path` from findings."""
    pyproject = find_pyproject(path)
    return _matches_config_glob(path, pyproject, _repostyle_table(pyproject), "exclude")


def _is_reuse_test_file(path: Path) -> bool:
    """Reports whether `path` can define a test or test support code."""
    return path.suffix == ".py" and _is_test_file(path)


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


def _test_name_terms(name: str) -> set[str]:
    """Returns the meaningful lowercase words in a test function name."""
    return {
        term.lower()
        for component in name.removeprefix("test_").split("_")
        for term in _TEST_NAME_TERM.findall(component)
        if term.lower() not in _GENERIC_TEST_NAME_TERMS
    }
