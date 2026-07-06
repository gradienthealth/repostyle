"""Resolves the enabled-rule set from config and lints paths with it."""

from __future__ import annotations

import tomllib
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path

from repostyle.rules import (
    ALL_RULE_IDS,
    FIXABLE_RULES,
    PACKAGE_RULES,
    RS_DOC_FILL,
    RS_NO_DOUBLE_BACKTICKS,
    RS_TERMINAL_PUNCTUATION,
    Violation,
    fix_comment_terminal_punctuation,
    fix_docstring_terminal_punctuation,
    fix_double_backticks,
    reflow_doc_fill,
    run_package_rule,
    run_rule,
)
from repostyle.rules._comments import COMMENT_SUFFIXES
from repostyle.rules._shared import find_pyproject
from repostyle.suppressions import filter_suppressed, suppressed_lines

# Each fixer rewrites one rule's findings, taking `(path, source,
# waived_lines)` and returning the rewritten source. They run in this
# order so the surface edits (backticks, terminal punctuation) settle
# before the reflow rewraps the corrected prose; each re-parses the
# source it is handed, so chaining their edits is safe.
_Fixer = Callable[[Path, str, frozenset[int]], str]
_FIXERS: tuple[tuple[str, _Fixer], ...] = (
    (RS_NO_DOUBLE_BACKTICKS, fix_double_backticks),
    (RS_TERMINAL_PUNCTUATION, fix_docstring_terminal_punctuation),
    (RS_TERMINAL_PUNCTUATION, fix_comment_terminal_punctuation),
    (RS_DOC_FILL, reflow_doc_fill),
)

# Directories never holding first-party source, skipped when building the
# whole-package index a package rule scans, and when expanding a directory
# argument into its lintable files.
_SKIPPED_DIRS = frozenset({"build", "dist", "__pycache__", "node_modules"})

# The suffixes a rule ever inspects: every `COMMENT_SUFFIXES` language plus
# markdown, which RS005 covers but the comment rules do not. A directory
# argument is expanded to files matching this set; an explicit file argument is
# linted regardless of suffix, since every rule already no-ops on a suffix it
# does not claim.
LINTABLE_SUFFIXES = COMMENT_SUFFIXES | {".md"}


def resolve_enabled_rules_for_paths(paths: Iterable[Path]) -> set[str]:
    """Discovers config from the first path's directory and resolves rules."""
    paths = list(paths)
    if not paths:
        return set(ALL_RULE_IDS)
    pyproject = find_pyproject(paths[0])
    config = load_config(pyproject) if pyproject is not None else None
    return resolve_enabled_rules(config)


def load_config(pyproject: Path) -> dict | None:
    """Reads the `[tool.repostyle]` table from a pyproject file."""
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    return data.get("tool", {}).get("repostyle")


def resolve_enabled_rules(config: dict | None) -> set[str]:
    """Resolves enabled rule ids from a `[tool.repostyle]` table.

    `select` defaults to every rule; `ignore` defaults to none. The enabled set
    is `select` minus `ignore`. A missing or empty table enables all rules. An
    unknown id in `select` or `ignore` raises `ValueError`: silently dropping
    it could resolve `select` to the empty set and make the linter pass
    everything.
    """
    if not config:
        return set(ALL_RULE_IDS)
    known = set(ALL_RULE_IDS)
    select = config.get("select")
    ignore = config.get("ignore", [])
    unknown = (set(select or ()) | set(ignore)) - known
    if unknown:
        raise ValueError(
            "unknown repostyle rule id(s): "
            f"{', '.join(sorted(unknown))}. Known ids: {', '.join(sorted(known))}."
        )
    selected = set(select) if select else known
    return selected - set(ignore)


def expand_paths(paths: Iterable[Path]) -> list[Path]:
    """Replaces each directory argument with the lintable files beneath it.

    Recurses each directory for files matching `LINTABLE_SUFFIXES`, skipping
    dot-directories and `_SKIPPED_DIRS`, and drops a duplicate resolved path
    reachable from more than one argument. A file argument passes through
    unchanged regardless of suffix.
    """
    expanded: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        candidates = sorted(_lintable_files(path)) if path.is_dir() else [path]
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            expanded.append(candidate)
    return expanded


def _lintable_files(root: Path) -> Iterator[Path]:
    return _walk_matching(root, LINTABLE_SUFFIXES)


def lint_paths(paths: Iterable[Path], enabled: set[str]) -> list[Violation]:
    return [v for path in paths for v in lint_path(path, enabled)]


def lint_path(path: Path, enabled: set[str]) -> list[Violation]:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    violations: list[Violation] = []
    for rule_id in enabled:
        violations.extend(run_rule(rule_id, path, source))
    violations = filter_suppressed(path, violations, source)
    return sorted(set(violations))


def lint_package(
    paths: Iterable[Path],
    enabled: set[str],
    *,
    root_paths: Iterable[Path] | None = None,
) -> dict[Path, list[Violation]]:
    """Runs the enabled whole-package rules, scoped to the given paths.

    A package rule sees every first-party file under the repo root so its
    cross-module view is whole, but findings are reported only on the paths
    passed in — keeping it sound under pre-commit's per-file batching. Returns
    findings keyed by each path's resolved location.

    Args:
        root_paths: locates the package root, defaulting to `paths`. Pass the
            pre-expansion arguments when `paths` has already been expanded from
            a directory, so the root is discovered from what the caller pointed
            at rather than an arbitrary file the expansion happened to sort
            first.
    """
    paths = list(paths)
    package_rules = enabled & set(PACKAGE_RULES)
    if not package_rules or not paths:
        return {}
    root_paths = list(root_paths) if root_paths is not None else paths
    root = find_pyproject(root_paths[0])
    files = _package_files(root.parent if root is not None else root_paths[0])
    sources = {path.resolve(): source for path, source in files}
    scope = {path.resolve() for path in paths}
    findings: dict[Path, list[Violation]] = {}
    for rule_id in package_rules:
        for path, violation in run_package_rule(rule_id, files):
            resolved = path.resolve()
            if resolved in scope:
                findings.setdefault(resolved, []).append(violation)
    kept = {
        path: sorted(set(filter_suppressed(path, violations, sources.get(path, ""))))
        for path, violations in findings.items()
    }
    return {path: violations for path, violations in kept.items() if violations}


def _package_files(root: Path) -> list[tuple[Path, str]]:
    """Reads every first-party Python file under `root`."""
    root = root.resolve()
    base = root if root.is_dir() else root.parent
    files: list[tuple[Path, str]] = []
    for path in sorted(_walk_matching(base, frozenset({".py"}))):
        try:
            files.append((path, path.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError):
            continue
    return files


def _walk_matching(root: Path, suffixes: frozenset[str]) -> Iterator[Path]:
    for path in root.rglob("*"):
        if _is_skipped_entry(path, root):
            continue
        if path.suffix in suffixes and path.is_file():
            yield path


def _is_skipped_entry(path: Path, base: Path) -> bool:
    """Reports whether `path` sits under a dot-directory or `_SKIPPED_DIRS`.

    Tests the parts below `base`, not the absolute ancestors: a repo checked
    out under a dot-directory (`.claude/worktrees/...`) must not have its whole
    tree skipped.
    """
    within = path.relative_to(base).parts
    return any(part.startswith(".") or part in _SKIPPED_DIRS for part in within)


def fix_path(path: Path, enabled: set[str]) -> bool:
    """Applies each enabled fixable rule to `path` in place, reporting change.

    A no-op unless a fixable rule is enabled and `path` is a Python, markdown,
    TOML, or YAML file. The fixers run in `_FIXERS` order, each handed the
    output of the last; on a TOML or YAML file only the RS009 comment reflow
    acts, the others being Python/markdown-only. A whole-file ignore directive
    leaves the file untouched for that rule, and a per-line suppression leaves
    its line untouched.
    """
    if not enabled & FIXABLE_RULES or path.suffix not in LINTABLE_SUFFIXES:
        return False
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    original = source
    for rule_id, fixer in _FIXERS:
        if rule_id not in enabled:
            continue
        file_suppressed, skip = suppressed_lines(path, source, rule_id)
        if file_suppressed:
            continue
        source = fixer(path, source, skip)
    if source == original:
        return False
    path.write_text(source, encoding="utf-8")
    return True
