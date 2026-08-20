"""Grandfathers a repo's pre-existing findings so only new ones fail.

A repo adopting a rule inherits whatever its tree already violates. Severity
cannot separate that backlog from new work -- a rule left advisory is
unenforced everywhere, and one promoted to error fails on the first commit that
touches an old file. The baseline separates them by record instead: a file
records how many findings of each rule the tree already had, and a run reports
only the findings above that count.

The record is a count per file per rule, never a line number, so an edit that
moves a finding does not resurrect it and a stale baseline never has to be
regenerated for churn alone. Removing a finding lowers the count on the next
refresh, which is the ratchet: the backlog only shrinks.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import NamedTuple

from repostyle.rules import Violation

DEFAULT_BASELINE_NAME = ".repostyle-baseline.json"

_SCHEMA = 1


class Baseline(NamedTuple):
    """A tree's grandfathered findings, counted per file per rule.

    `counts` maps a repo-root-relative POSIX path to a rule id to the number of
    findings that path held when the baseline was written. `rules` is the rule
    set the baseline was built against, so a later refresh can tell a rule that
    did not exist then from one whose findings are new.
    """

    rules: frozenset[str]
    counts: dict[str, dict[str, int]]


def load(path: Path) -> Baseline | None:
    """Reads a baseline file, returning `None` when it cannot be used.

    A missing, unreadable, or malformed file returns `None` rather than
    raising, so a run with no baseline behaves as if nothing were
    grandfathered. The caller distinguishes the two by checking whether the
    path exists.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("schema") != _SCHEMA:
        return None
    rules = data.get("rules")
    counts = data.get("counts")
    if not isinstance(rules, list) or not isinstance(counts, dict):
        return None
    return Baseline(
        rules=frozenset(str(rule) for rule in rules),
        counts={
            str(file): {
                str(rule): int(count)
                for rule, count in per_rule.items()
                if isinstance(count, int) and count > 0
            }
            for file, per_rule in counts.items()
            if isinstance(per_rule, dict)
        },
    )


def save(path: Path, baseline: Baseline) -> None:
    """Writes a baseline file, sorted so a refresh produces a readable diff."""
    payload = {
        "schema": _SCHEMA,
        "rules": sorted(baseline.rules),
        "counts": {
            file: dict(sorted(baseline.counts[file].items()))
            for file in sorted(baseline.counts)
            if baseline.counts[file]
        },
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def build(
    findings: dict[Path, list[Violation]], root: Path, rules: frozenset[str]
) -> Baseline:
    """Counts `findings` per file per rule into a fresh baseline."""
    counts: dict[str, dict[str, int]] = {}
    for path, violations in findings.items():
        if not violations:
            continue
        counts[_key(path, root)] = dict(
            Counter(violation.rule for violation in violations)
        )
    return Baseline(rules=frozenset(rules), counts=counts)


def refresh(existing: Baseline, current: Baseline) -> Baseline:
    """Merges a fresh scan into an existing baseline, admitting only new rules.

    A count drops to whatever the tree now holds, so fixing a finding retires
    its slot permanently. A count rises only for a rule absent from the rule
    set of `existing` -- a rule the linter gained since the baseline was
    written, whose backlog was never anyone's regression. A rule the baseline
    already knew keeps its old ceiling, so new code cannot grandfather itself
    by refreshing.
    """
    merged: dict[str, dict[str, int]] = {}
    for file in set(existing.counts) | set(current.counts):
        was = existing.counts.get(file, {})
        now = current.counts.get(file, {})
        per_rule = {}
        for rule, count in now.items():
            ceiling = count if rule not in existing.rules else was.get(rule, 0)
            allowed = min(count, ceiling)
            if allowed > 0:
                per_rule[rule] = allowed
        if per_rule:
            merged[file] = per_rule
    return Baseline(rules=existing.rules | current.rules, counts=merged)


def filter_baselined(
    path: Path, violations: list[Violation], baseline: Baseline, root: Path
) -> list[Violation]:
    """Drops each path's grandfathered findings, keeping the excess.

    Within one rule the findings kept are the last ones in file order. Which
    specific finding survives is arbitrary -- the baseline records a count, not
    an identity -- but reporting the tail means an addition at the top of a
    file is not mistaken for the one already grandfathered at the bottom.
    """
    allowance = dict(baseline.counts.get(_key(path, root), {}))
    kept: list[Violation] = []
    for violation in violations:
        remaining = allowance.get(violation.rule, 0)
        if remaining > 0:
            allowance[violation.rule] = remaining - 1
            continue
        kept.append(violation)
    return kept


def _key(path: Path, root: Path) -> str:
    """Returns `path` as a POSIX path relative to `root`, or its resolved name.

    A path outside `root` keeps its absolute form, which no relative key can
    collide with, so a file linted from outside the repo is simply never
    grandfathered.
    """
    resolved = path.resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()
