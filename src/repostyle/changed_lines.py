"""Map a file to the new-file line numbers a git diff added or modified.

This backs the CLI's `--diff` mode: a finding is reported only when its own
line is one the change touched, so adopting a rule does not block a pull
request on its pre-existing backlog. The intersection is on the finding's own
line — a whole-unit finding reported at a `def` re-arms only when that line
changes, not on an edit elsewhere in its body.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

_HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")


def changed_lines(path: Path, base: str) -> set[int] | None:
    """Return the new-file line numbers `path` adds or modifies versus `base`.

    Return `None` when the change set cannot be trusted — git is unavailable,
    `base` is unknown, or `path` is untracked — so the caller reports every
    finding rather than hide one. A tracked file with no diff against `base`
    returns an empty set.
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
