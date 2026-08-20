"""Maps a file to the new-file line numbers a git diff added or modified.

This backs the CLI's `--diff` mode: a finding is reported only when its own
line is one the change touched, so adopting a rule does not block a pull
request on its pre-existing backlog. The intersection is on the finding's own
line -- a whole-unit finding reported at a `def` re-arms only when that line
changes, not on an edit elsewhere in its body.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

_HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")

# Refs tried, in order, when no `--diff-base` is given. The remote's recorded
# default branch comes first; the rest cover a repo whose `origin/HEAD` was
# never set, and a clone with no remote at all.
_BASE_CANDIDATES = ("origin/main", "origin/master", "main", "master")


def resolve_diff_base(start: Path, requested: str | None) -> str | None:
    """Returns the commit `--diff` compares against, or `None` if unresolved.

    The default is the merge-base of `HEAD` and the repo's default branch,
    which is the commit a pull request branched from -- the same scope whether
    the run is a local commit hook or a CI pass over a checked-out branch.
    Comparing against `HEAD` instead would report nothing at all in CI, where
    the tree is clean.

    Args:
        start: A path inside the repo to resolve the base against.
        requested: An explicit ref, verified rather than trusted so an unknown
            one refuses the run instead of silently widening its scope.

    Returns:
        The resolved commit, or `None` when the ref is unknown, no default
        branch is reachable (a shallow clone that never fetched one), or the
        path is not in a git work tree.
    """
    directory = start if start.is_dir() else start.parent
    if requested is not None:
        return requested if _rev_parse(requested, directory) else None
    for ref in _base_candidates(directory):
        merge_base = _run_git(["merge-base", "HEAD", ref], directory)
        if merge_base.returncode == 0:
            return merge_base.stdout.strip()
    return None


def _base_candidates(directory: Path) -> tuple[str, ...]:
    """Returns the refs to try as a default branch, best candidate first."""
    recorded = _run_git(
        ["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], directory
    )
    if recorded.returncode != 0:
        return _BASE_CANDIDATES
    return (recorded.stdout.strip(), *_BASE_CANDIDATES)


def _rev_parse(ref: str, directory: Path) -> bool:
    """Reports whether `ref` names a commit in the repo holding `directory`."""
    probe = _run_git(["rev-parse", "--verify", f"{ref}^{{commit}}"], directory)
    return probe.returncode == 0


def changed_lines(path: Path, base: str) -> set[int] | None:
    """Returns the new-file line numbers `path` adds or modifies versus `base`.

    Returns:
        `None` when the change set cannot be trusted -- git is unavailable,
        `base` is unknown, or `path` is untracked -- so the caller reports
        every finding rather than hide one, or an empty set for a tracked file
        with no diff against `base`.
    """
    diff = _run_git(["diff", "--unified=0", base, "--", path.name], path.parent)
    if diff.returncode != 0:
        return None
    lines: set[int] = set()
    new_lineno = 0
    for line in diff.stdout.splitlines():
        header = _HUNK_HEADER.match(line)
        if header is not None:
            new_lineno = int(header.group(1))
        elif line.startswith("+") and not line.startswith("+++"):
            lines.add(new_lineno)
            new_lineno += 1
    if not lines:
        # An untracked file has no diff at all, so an empty result is the only
        # case mistakable for an unchanged tracked file; fail open when the
        # file proves untracked.
        tracked = _run_git(
            ["ls-files", "--error-unmatch", "--", path.name], path.parent
        )
        if tracked.returncode != 0:
            return None
    return lines


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
