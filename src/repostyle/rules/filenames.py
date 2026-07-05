"""Filename-convention rule: preferred extensions and multi-word casing.

Two checks bundled under RS033, both scoped to a file's name on disk rather
than its content, and both skip `.py` files — a Python module's name is already
governed by import-identifier conventions elsewhere. Each check reads its own
`[tool.repostyle]` config key and falls back to a shipped default when the key
is absent, rather than reporting nothing: the defaults reflect a documented,
spec- or style-guide-level convention rather than a Gradient-specific house
preference, so a repo that never configures this rule still gets a defensible
baseline. A repo that disagrees overrides the relevant key; one with fixed-name
files a tool mandates (`Dockerfile`, `LICENSE`, a generated `CHANGELOG.md`)
exempts them via `filename-ignore` rather than renaming them.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Iterator
from fnmatch import fnmatch
from functools import lru_cache
from pathlib import Path

from repostyle.rules._shared import _posix, find_pyproject
from repostyle.rules._violation import RS_FILENAME_CONVENTION, Violation

# yaml.org's FAQ has recommended `.yaml` as the extension since 2006; `.yml`
# survives only as a holdover from the old DOS/Windows 8.3 filename-length
# limit, a constraint that no longer applies. A repo replaces this table
# wholesale via `[tool.repostyle.filename-extensions]`; an explicit empty table
# disables the check.
DEFAULT_EXTENSION_MAP: dict[str, str] = {".yml": ".yaml"}

# Google's developer documentation style guide prefers hyphens over underscores
# in filenames, since a search engine reads a hyphen as a word break but not an
# underscore. `[tool.repostyle.filename-case]` overrides this with `"snake"`,
# or disables the check with any other value (`"none"` is the documented
# spelling).
DEFAULT_FILENAME_CASE = "kebab"

_WORD_PATTERN = {
    "kebab": re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$"),
    "snake": re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*$"),
}


def check_filename_extension(path: Path, source: str) -> Iterator[Violation]:
    """Flag a file extension the configured mapping prefers replaced.

    The mapping is a disallowed-extension-to-preferred-extension table read
    from `[tool.repostyle.filename-extensions]`, defaulting to `.yml` ->
    `.yaml`. A `.py` file and a path matched by `filename-ignore` are exempt.
    """
    if path.suffix == ".py" or _is_ignored(path):
        return
    table = _repostyle_table(find_pyproject(path))
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
    """Flag a filename whose dot-separated words are not uniformly cased.

    The casing (`"kebab"` or `"snake"`) is read from
    `[tool.repostyle.filename-case]`, defaulting to kebab-case; any other
    value, including the documented `"none"`, disables the check. A `.py` file
    and a path matched by `filename-ignore` are exempt. A leading dot marking a
    hidden file (`.pre-commit-config.yaml`) is not itself a word boundary.
    """
    if path.suffix == ".py" or _is_ignored(path):
        return
    table = _repostyle_table(find_pyproject(path))
    case = _filename_case(table)
    pattern = _WORD_PATTERN.get(case)
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
    configured = table.get("filename-extensions")
    if configured is None:
        return DEFAULT_EXTENSION_MAP
    return {str(key).lower(): str(value) for key, value in configured.items()}


def _filename_case(table: dict[str, object]) -> str:
    return str(table.get("filename-case", DEFAULT_FILENAME_CASE))


def _is_ignored(path: Path) -> bool:
    pyproject = find_pyproject(path)
    table = _repostyle_table(pyproject)
    globs = _ignore_globs(table)
    if not globs:
        return False
    relative = _relative_to_pyproject(path, pyproject)
    return any(fnmatch(relative, glob) for glob in globs)


def _ignore_globs(table: dict[str, object]) -> tuple[str, ...]:
    return tuple(str(glob) for glob in table.get("filename-ignore", ()))


def _name_segments(stem: str) -> list[str]:
    """Split a stem on `.` into its words, dropping a leading hidden-file dot."""
    segments = stem.split(".")
    if segments and segments[0] == "":
        segments = segments[1:]
    return [segment for segment in segments if segment]


def _relative_to_pyproject(path: Path, pyproject: Path | None) -> str:
    if pyproject is None:
        return _posix(path)
    try:
        return _posix(path.resolve().relative_to(pyproject.parent))
    except ValueError:
        return _posix(path)


@lru_cache(maxsize=128)
def _repostyle_table(pyproject: Path | None) -> dict[str, object]:
    """Read the `[tool.repostyle]` table from a pyproject file, if any."""
    if pyproject is None:
        return {}
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return data.get("tool", {}).get("repostyle", {})
