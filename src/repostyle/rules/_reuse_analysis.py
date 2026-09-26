"""Groups test functions by reusable structure."""

from __future__ import annotations

import ast
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
    _ReuseFunction,
    _unsupported_reuse,
)
from repostyle.rules._test_reuse_keys import (
    _function_key,
    _without_docstring,
)


def internal_maximal_setup_groups(
    scoped: list[InternalSetupCandidate],
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
        if len(unique) < InternalTEST_REUSE_MINIMUM:
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


InternalTEST_REUSE_MINIMUM = 3


@dataclass(frozen=True)
class InternalSetupCandidate:
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


def internal_shared_helper_candidates(
    files: Sequence[tuple[Path, str]],
) -> Iterator[_SharedHelperCandidate]:
    """Yields each eligible helper beside its category and syntax key."""
    for path, source in files:
        if not internal_is_reuse_test_file(path) or _is_excluded_reuse_file(path):
            continue
        for function in internal_reuse_functions(path, source):
            candidate = _shared_helper_candidate(function)
            if candidate is not None:
                yield candidate


def _is_excluded_reuse_file(path: Path) -> bool:
    """Reports whether config excludes `path` from findings."""
    pyproject = find_pyproject(path)
    return _matches_config_glob(path, pyproject, _repostyle_table(pyproject), "exclude")


def internal_is_reuse_test_file(path: Path) -> bool:
    """Reports whether `path` can define a test or test support code."""
    return path.suffix == ".py" and _is_test_file(path)


def internal_reuse_functions(path: Path, source: str) -> list[_ReuseFunction]:
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


def _shared_helper_candidate(function: _ReuseFunction) -> _SharedHelperCandidate | None:
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


_HELPER_STATEMENT_MINIMUM = 3


@dataclass(frozen=True)
class _SharedHelperCandidate:
    """Carries one helper category, syntax key, and source function."""

    category: str
    key: object
    function: _ReuseFunction


def internal_test_name_terms(name: str) -> set[str]:
    """Returns the meaningful lowercase words in a test function name."""
    return {
        term.lower()
        for component in name.removeprefix("test_").split("_")
        for term in _TEST_NAME_TERM.findall(component)
        if term.lower() not in _GENERIC_TEST_NAME_TERMS
    }


_TEST_NAME_TERM = re.compile("[A-Z]+(?=[A-Z][a-z]|\\b)|[A-Z]?[a-z]+|\\d+")

_GENERIC_TEST_NAME_TERMS = frozenset(
    {"checked", "flags", "no", "not", "nothing", "reports", "violation"}
)
