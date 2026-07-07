"""Filename-convention rule: preferred extensions and multi-word casing.

Two checks bundled under RS033, both scoped to a file's name on disk rather
than its content, and both skip `.py` files — a Python module's name is already
governed by import-identifier conventions elsewhere. Each check reads its own
`[tool.repostyle]` config key and falls back to a shipped default when the key
is absent, rather than reporting nothing: the defaults reflect a documented,
spec- or style-guide-level convention rather than a Gradient-specific house
preference, so a repo that never configures this rule still gets a defensible
baseline. A repo that disagrees overrides the relevant key. A file whose name a
tool or ecosystem convention fixes (`README.md`, `CLAUDE.md`) is exempt from
both checks by default via `DEFAULT_EXEMPT_FILENAMES`; a repo extends that set
through `filename-ignore` for any further fixed-name file rather than renaming
it.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from repostyle.rules._shared import (
    _matches_config_glob,
    _repostyle_table,
    find_pyproject,
)
from repostyle.rules._violation import RS_FILENAME_CONVENTION, Violation

# yaml.org's FAQ has recommended `.yaml` as the extension since 2006; `.yml`
# survives only as a holdover from the old DOS/Windows 8.3 filename-length
# limit, a constraint that no longer applies. A repo replaces this table
# wholesale via `[tool.repostyle.filename-extensions]`; an explicit empty table
# disables the check.
DEFAULT_EXTENSION_MAP: dict[str, str] = {".yml": ".yaml"}

# Google's developer documentation style guide prefers hyphens over underscores
# in filenames, since a search engine reads a hyphen as a word break but not an
# underscore. `filename-case` overrides this with `"snake"`, or disables the
# check with any other value (`"none"` is the documented spelling).
DEFAULT_FILENAME_CASE = "kebab"

# Basenames whose spelling is fixed by an external tool or an ecosystem
# convention rather than by the repo's own naming choice, so neither the casing
# nor the extension check applies: renaming them to satisfy this rule would
# break the tool that looks them up. GitHub resolves the community-health files
# (`CONTRIBUTING`, `CODE_OF_CONDUCT`, `SECURITY`) plus `CODEOWNERS` and
# `LICENSE` by exact name; `README`/`CHANGELOG` follow the all-caps Unix/GNU
# metadata convention; and `CLAUDE.md`/`AGENTS.md` are looked up verbatim by
# their respective agent tooling. Matched case-sensitively on the basename, as
# the ecosystem writes them. A repo extends this set through `filename-ignore`;
# it never needs to re-list these.
DEFAULT_EXEMPT_FILENAMES: frozenset[str] = frozenset(
    {
        "README.md",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
        "SECURITY.md",
        "LICENSE",
        "CODEOWNERS",
        "CLAUDE.md",
        "AGENTS.md",
    }
)

_WORD_PATTERNS = {
    "kebab": re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$"),
    "snake": re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*$"),
}


def check_filename_extension(path: Path, source: str) -> Iterator[Violation]:
    """Flags a file extension the configured mapping prefers replaced.

    The mapping is a disallowed-extension-to-preferred-extension table read
    from `[tool.repostyle.filename-extensions]`, defaulting to `.yml` ->
    `.yaml`. A `.py` file, a basename in `DEFAULT_EXEMPT_FILENAMES`, and a path
    matched by `filename-ignore` are exempt.
    """
    table = _resolve_table(path)
    if table is None:
        return
    preferred = _extension_map(table).get(path.suffix.lower())
    if preferred is None or preferred.lower() == path.suffix.lower():
        return
    yield Violation(
        1,
        1,
        RS_FILENAME_CONVENTION,
        f"'{path.name}' uses the '{path.suffix}' extension; rename to "
        f"'{path.stem}{preferred}'",
    )


def check_filename_casing(path: Path, source: str) -> Iterator[Violation]:
    """Flags a filename stem whose segments don't match the configured case.

    The casing (`"kebab"` or `"snake"`) is read from `filename-case`,
    defaulting to kebab-case; any other value, including the documented
    `"none"`, disables the check. A `.py` file, a basename in
    `DEFAULT_EXEMPT_FILENAMES`, and a path matched by `filename-ignore` are
    exempt. A leading dot marking a hidden file (`.pre-commit-config.yaml`) is
    not itself a word boundary.
    """
    table = _resolve_table(path)
    if table is None:
        return
    case = _filename_case(table)
    pattern = _WORD_PATTERNS.get(case)
    if pattern is None:
        return
    segments = _name_segments(path.stem)
    if all(pattern.match(segment) for segment in segments):
        return
    yield Violation(
        1,
        1,
        RS_FILENAME_CONVENTION,
        f"'{path.name}' should use {case}-case for a multi-word name",
    )


def _extension_map(table: dict[str, object]) -> dict[str, str]:
    configured = table.get("filename-extensions", DEFAULT_EXTENSION_MAP)
    if not isinstance(configured, dict):
        return {}
    return {str(key).lower(): str(value) for key, value in configured.items()}


def _filename_case(table: dict[str, object]) -> str:
    return str(table.get("filename-case", DEFAULT_FILENAME_CASE)).lower()


def _resolve_table(path: Path) -> dict[str, object] | None:
    """Returns the `[tool.repostyle]` table for `path`, or `None` if exempt."""
    if path.suffix == ".py" or path.name in DEFAULT_EXEMPT_FILENAMES:
        return None
    pyproject = find_pyproject(path)
    table = _repostyle_table(pyproject)
    if _is_ignored(path, pyproject, table):
        return None
    return table


def _is_ignored(path: Path, pyproject: Path | None, table: dict[str, object]) -> bool:
    return _matches_config_glob(path, pyproject, table, "filename-ignore")


def _name_segments(stem: str) -> list[str]:
    """Splits a stem on `.` into its segments, dropping any empty segment."""
    return [segment for segment in stem.split(".") if segment]
