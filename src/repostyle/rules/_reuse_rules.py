"""Detects repeated setup and reusable test helpers."""

from __future__ import annotations

import itertools
from collections import defaultdict
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from repostyle._shared import (
    find_config_file,
)
from repostyle.rules._reuse_analysis import (
    InternalSetupCandidate,
    InternalTEST_REUSE_MINIMUM,
    internal_is_reuse_test_file,
    internal_maximal_setup_groups,
    internal_reuse_functions,
    internal_shared_helper_candidates,
    internal_test_name_terms,
)
from repostyle.rules._test_reuse_context import (
    _is_parametrized,
    _ReuseFunction,
    _unsupported_reuse,
)
from repostyle.rules._test_reuse_keys import (
    _parametrization_key,
    _setup_prefix,
)
from repostyle.rules._violation import (
    RS_REPEATED_TEST_SETUP,
    RS_SHARED_TEST_HELPER,
    RS_TEST_PARAMETRIZATION_CANDIDATE,
    Violation,
)


def check_repeated_test_setup(path: Path, source: str) -> Iterator[Violation]:
    """Warns about repeated leading assignment sequences in tests.

    Three tests in one module or class scope qualify when at least two exact
    leading simple assignments match and the shared prefix includes a call. The
    finding prompts review for a builder or fixture without deciding that the
    call is setup or prescribing fixture lifetime.
    """
    if not internal_is_reuse_test_file(path):
        return
    by_scope: dict[str, list[InternalSetupCandidate]] = defaultdict(list)
    for function in internal_reuse_functions(path, source):
        if not function.node.name.startswith("test_") or _unsupported_reuse(function):
            continue
        prefix, first_call_assignment = _setup_prefix(function)
        if len(prefix) >= 2:
            by_scope[function.scope].append(
                InternalSetupCandidate(function, prefix, first_call_assignment)
            )
    for scoped in by_scope.values():
        for group in internal_maximal_setup_groups(scoped):
            for function in group.reported_members:
                yield Violation(
                    function.node.lineno,
                    function.node.col_offset + 1,
                    RS_REPEATED_TEST_SETUP,
                    f"test repeats {group.assignment_count} leading assignments across {len(group.members)} cases; consider a builder or fixture",
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
    for candidate in internal_shared_helper_candidates(files):
        groups[candidate.category, candidate.key].append(candidate.function)
    for (kind, _), members in groups.items():
        ordered = sorted(
            members, key=lambda item: (item.path.as_posix(), item.node.lineno)
        )
        if len({member.path.resolve() for member in ordered}) < 2:
            continue
        for member in ordered:
            peer = next(item for item in ordered if item.path != member.path)
            message = f"{kind} candidate matches {len(ordered)} definitions across test files, including {_display_location(peer)}; consider one shared {kind}"
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
    if not internal_is_reuse_test_file(path):
        return
    groups: dict[object, list[_ParametrizationCandidate]] = defaultdict(list)
    for function in internal_reuse_functions(path, source):
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


def _contract_groups(
    members: list[_ParametrizationCandidate],
) -> list[list[_ParametrizationCandidate]]:
    """Returns maximal groups that share a two-term contract stem."""
    by_term_pair: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, member in enumerate(members):
        terms = sorted(internal_test_name_terms(member.function.node.name))
        for pair in itertools.combinations(terms, 2):
            by_term_pair[pair].append(index)
    qualifying = {
        frozenset(group)
        for group in by_term_pair.values()
        if len(group) >= InternalTEST_REUSE_MINIMUM
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
        if len(unclaimed) < InternalTEST_REUSE_MINIMUM:
            continue
        claimed.update(unclaimed)
        selected.append([members[index] for index in unclaimed])
    return selected


def _display_location(function: _ReuseFunction) -> str:
    """Returns a repository-relative peer location."""
    pyproject = find_config_file(function.path)
    try:
        displayed = function.path.relative_to(pyproject.parent) if pyproject else None
    except ValueError:
        displayed = None
    path = (displayed or function.path).as_posix()
    if len(path) > _TEST_REUSE_PATH_LIMIT:
        path = f"…{path[-(_TEST_REUSE_PATH_LIMIT - 1) :]}"
    return f"{path}:{function.node.lineno}"


_TEST_REUSE_PATH_LIMIT = 80


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
            f"test matches {len(members)} cases that differ only in scalar body literals; consider `pytest.mark.parametrize` while retaining distinct contracts",
        )


@dataclass(frozen=True)
class _ParametrizationCandidate:
    """Pairs one test with the scalar values its syntax key abstracted."""

    function: _ReuseFunction
    literal_values: tuple[str, ...]


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
