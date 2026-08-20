"""Resolves the enabled-rule set from config and lints paths with it."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import NamedTuple

from repostyle._comments import COMMENT_SUFFIXES
from repostyle._shared import (
    _bool_config,
    _dir_matches_config_glob,
    _gitignore_prunes_dir,
    _GitignoreRules,
    _matches_config_glob,
    _parse_gitignore,
    _repostyle_table,
    find_pyproject,
)
from repostyle.baseline import DEFAULT_BASELINE_NAME
from repostyle.rules import (
    ALL_RULE_IDS,
    FIXABLE_RULES,
    PACKAGE_RULES,
    RS_ACRONYM_CASING_IN_PROSE,
    RS_DISFAVORED_GCP_TERM,
    RS_DOC_FILL,
    RS_DOCSTRING_SECTION_ALIAS,
    RS_DOUBLE_SPACE_AFTER_PERIOD,
    RS_NO_DOUBLE_BACKTICKS,
    RS_NONSTANDARD_DASH,
    RS_TERMINAL_PUNCTUATION,
    Violation,
    fix_acronym_casing_in_comments,
    fix_acronym_casing_in_docstrings,
    fix_comment_terminal_punctuation,
    fix_disfavored_gcp_term_in_comments,
    fix_disfavored_gcp_term_in_docstrings,
    fix_doc_fill,
    fix_docstring_section_alias,
    fix_docstring_terminal_punctuation,
    fix_double_backticks,
    fix_double_space_in_comments,
    fix_double_space_in_docstrings,
    fix_nonstandard_dash_in_comments,
    fix_nonstandard_dash_in_docstrings,
    run_package_rule,
    run_rule,
)
from repostyle.suppressions import filter_suppressed, suppressed_lines

# Each fixer rewrites one rule's findings, taking `(path, source,
# skip_lines)` and returning the rewritten source. They run in this
# order so the surface edits (backticks, dashes, terminal punctuation)
# settle before the reflow rewraps the corrected prose -- a dash rewrite
# changes line length, so the reflow must run after it; each re-parses
# the source it is handed, so chaining their edits is safe.
_Fixer = Callable[[Path, str, frozenset[int]], str]
_FIXERS: tuple[tuple[str, _Fixer], ...] = (
    (RS_NO_DOUBLE_BACKTICKS, fix_double_backticks),
    (RS_DOCSTRING_SECTION_ALIAS, fix_docstring_section_alias),
    (RS_ACRONYM_CASING_IN_PROSE, fix_acronym_casing_in_docstrings),
    (RS_ACRONYM_CASING_IN_PROSE, fix_acronym_casing_in_comments),
    (RS_DISFAVORED_GCP_TERM, fix_disfavored_gcp_term_in_docstrings),
    (RS_DISFAVORED_GCP_TERM, fix_disfavored_gcp_term_in_comments),
    (RS_NONSTANDARD_DASH, fix_nonstandard_dash_in_docstrings),
    (RS_NONSTANDARD_DASH, fix_nonstandard_dash_in_comments),
    (RS_TERMINAL_PUNCTUATION, fix_docstring_terminal_punctuation),
    (RS_TERMINAL_PUNCTUATION, fix_comment_terminal_punctuation),
    (RS_DOUBLE_SPACE_AFTER_PERIOD, fix_double_space_in_docstrings),
    (RS_DOUBLE_SPACE_AFTER_PERIOD, fix_double_space_in_comments),
    (RS_DOC_FILL, fix_doc_fill),
)

# Directories never holding first-party source, pruned during traversal when
# building the whole-package index a package rule scans and when expanding a
# directory argument into its lintable files. The dot-prefixed names are
# version-control metadata and the caches and virtualenvs a working tree
# accumulates. Every other dot-directory is walked, because a repo keeps linted
# files in one: pre-commit hands this linter the workflow YAML under `.github`
# and the markdown under `.claude`, and a walk that skipped them would put a
# finding the gate reports beyond the reach of `--update-baseline`, which can
# only grandfather what it walks. A worktree nested under one of those is
# pruned by `_is_nested_checkout` instead, on the structure rather than on the
# name of the directory holding it.
_SKIPPED_DIRS = frozenset(
    {
        "build",
        "dist",
        "__pycache__",
        "node_modules",
        "venv",
        ".git",
        ".hg",
        ".svn",
        ".venv",
        ".tox",
        ".nox",
        ".eggs",
        ".cache",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".pytype",
        ".hypothesis",
        ".direnv",
        ".terraform",
        ".gradle",
        ".next",
        ".idea",
        ".vscode",
    }
)

# The suffixes a rule ever inspects: every `COMMENT_SUFFIXES` language plus
# markdown, which RS005 covers but the comment rules do not. A directory
# argument is expanded to files matching this set; an explicit file argument is
# linted regardless of suffix, since every rule already no-ops on a suffix it
# does not claim.
LINTABLE_SUFFIXES = COMMENT_SUFFIXES | {".md"}


class _ResolvedRules(NamedTuple):
    """The rules to run and the subset promoted to error severity.

    `enabled` is `select` minus `ignore`; `promoted` holds the ids that print
    as errors and fail the run even where their default severity is warning --
    every id, or the `error` list alone under `warnings-as-errors = false`.
    """

    enabled: set[str]
    promoted: set[str]


def resolve_enabled_rules_for_paths(paths: Iterable[Path]) -> set[str]:
    """Discovers config from the first path's directory and resolves rules."""
    return resolve_rules_for_paths(paths).enabled


def resolve_rules_for_paths(paths: Iterable[Path]) -> _ResolvedRules:
    """Discovers config from the first path's directory and resolves rules.

    Loads the `[tool.repostyle]` table once and derives both the enabled set
    and the error-promotion set from it, so the config is read a single time.
    """
    paths = list(paths)
    if not paths:
        return _ResolvedRules(set(ALL_RULE_IDS), set(ALL_RULE_IDS))
    pyproject = find_pyproject(paths[0])
    config = load_config(pyproject) if pyproject is not None else None
    return _ResolvedRules(resolve_enabled_rules(config), resolve_promoted_rules(config))


def resolve_baseline_path(paths: Iterable[Path]) -> Path | None:
    """Returns the baseline file the repo holding `paths` uses, if any.

    The path is `[tool.repostyle] baseline` resolved against the directory of
    the `pyproject.toml` that declares it, so a run from any directory reads
    one file. An unset key falls back to `DEFAULT_BASELINE_NAME` beside the
    `pyproject.toml`, which is only consulted when it exists, so a repo that
    has not adopted a baseline needs no config.
    """
    paths = list(paths)
    if not paths:
        return None
    pyproject = find_pyproject(paths[0])
    if pyproject is None:
        return None
    configured = _repostyle_table(pyproject).get("baseline")
    if isinstance(configured, str) and configured:
        return pyproject.parent / configured
    default = pyproject.parent / DEFAULT_BASELINE_NAME
    return default if default.is_file() else None


def repo_root(paths: Iterable[Path]) -> Path:
    """Returns the directory baseline keys are relative to.

    The `pyproject.toml` directory is the root, falling back to the first
    path's own directory outside a project, so a key is stable wherever the run
    is invoked from.
    """
    paths = list(paths)
    if not paths:
        return Path.cwd()
    pyproject = find_pyproject(paths[0])
    if pyproject is not None:
        return pyproject.parent
    first = paths[0].resolve()
    return first if first.is_dir() else first.parent


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
    is `select` minus `ignore`. A missing or empty table enables all rules.

    Raises:
        ValueError: When `select` or `ignore` names an unknown id. Silently
            dropping it could resolve `select` to the empty set and make the
            linter pass everything.
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


def resolve_promoted_rules(config: dict | None) -> set[str]:
    """Resolves the ids promoted to error from a `[tool.repostyle]` table.

    Every selected rule is an error by default, so a repo gates on the rule set
    it selects rather than on a severity split it did not choose. The backlog
    that default would otherwise fail on is held by the baseline instead, which
    separates old findings from new ones by record rather than by severity.

    `warnings-as-errors = false` restores the per-rule default severities, and
    `error` then lists the advisory rules to promote anyway. Promoting a
    natively-error rule is a harmless no-op, and a disabled rule may be
    promoted (the promotion is inert until the rule fires).

    Raises:
        ValueError: When `error` names an unknown id, matching how
            `resolve_enabled_rules` validates `select` and `ignore`.
    """
    known = set(ALL_RULE_IDS)
    if not config:
        return known
    promoted = set(config.get("error", []))
    unknown = promoted - known
    if unknown:
        raise ValueError(
            "unknown repostyle rule id(s): "
            f"{', '.join(sorted(unknown))}. Known ids: {', '.join(sorted(known))}."
        )
    return promoted if config.get("warnings-as-errors") is False else known


def expand_paths(paths: Iterable[Path]) -> list[Path]:
    """Replaces each directory argument with the lintable files beneath it.

    Recurses each directory for files matching `LINTABLE_SUFFIXES`, skipping
    the `_SKIPPED_DIRS` names and any nested checkout, and drops a duplicate
    resolved path reachable from more than one argument. A file argument passes
    through unchanged regardless of suffix. A file matching a
    `[tool.repostyle] exclude` glob is dropped whether it was walked from a
    directory or passed explicitly.
    """
    expanded: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        candidates = sorted(_lintable_files(path)) if path.is_dir() else [path]
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved in seen or _is_excluded(candidate):
                continue
            seen.add(resolved)
            expanded.append(candidate)
    return expanded


def _is_excluded(path: Path) -> bool:
    """Reports whether `path` is excluded from scanning by its config table.

    Matches `path` against the `[tool.repostyle] exclude` globs of its nearest
    `pyproject.toml`. An `exclude` match drops the file from every rule, not
    just the RS033 filename rule that `filename-ignore` governs.
    """
    pyproject = find_pyproject(path)
    return _matches_config_glob(path, pyproject, _repostyle_table(pyproject), "exclude")


def _lintable_files(root: Path) -> Iterator[Path]:
    return _walk_matching(root, LINTABLE_SUFFIXES, should_apply_excludes=True)


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
    passed in -- keeping it sound under pre-commit's per-file batching. Returns
    findings keyed by each path's resolved location.

    Args:
        paths: The files findings are reported on, the pre-commit batch.
        enabled: The resolved rule set; only its package rules run here.
        root_paths: Locates the package root, defaulting to `paths`. Pass the
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
    """Reads every first-party Python file under `root`.

    Passes `should_apply_excludes=False`, so a file an `exclude` glob silences
    is still read into the whole-package index. That asymmetry is deliberate: a
    public name used only by excluded generated code (a `_grpc`/`_pb2` stub)
    must still count as a cross-module reference, or RS029 would flag it
    should-be-private on the strength of the exclude alone. The structural
    `_SKIPPED_DIRS` and nested-checkout prunes and, under `respect-gitignore`,
    the `.gitignore` prune still apply, so a working-tree `venv`, a second
    checkout of the repo, or a gitignored tree is not read: each is outside
    this package, unlike an excluded file.
    """
    root = root.resolve()
    base = root if root.is_dir() else root.parent
    files: list[tuple[Path, str]] = []
    for path in sorted(
        _walk_matching(base, frozenset({".py"}), should_apply_excludes=False)
    ):
        try:
            files.append((path, path.read_text(encoding="utf-8")))
        except (OSError, UnicodeDecodeError):
            continue
    return files


def _walk_matching(
    root: Path, suffixes: frozenset[str], *, should_apply_excludes: bool
) -> Iterator[Path]:
    """Yields the files under `root` matching `suffixes`, pruning as it walks.

    Descends with `os.walk`, dropping a pruned directory subtree before its
    files are enumerated: a `_SKIPPED_DIRS` name (a `venv`, `node_modules`, a
    build output, or a dot-prefixed cache) is never entered, so its files are
    never stat-ed or read. A directory holding its own `.git` is pruned the
    same way, so a nested checkout is not walked as part of this repo. Pruning
    during the walk keeps a run over a venv-heavy working tree from going
    CPU-bound (DEV-1522). A dot-prefixed file matching `suffixes` is walked
    like any other, so a repo's `.pre-commit-config.yaml` is linted where it
    sits.

    When the config sets `respect-gitignore`, a directory the repo's root
    `.gitignore` names is pruned too, on both walks -- a gitignored tree is
    treated as not part of the repo at all, so it is invisible even to the
    whole-package index. That is the opposite of `exclude`, which keeps a file
    in the tree and only silences its findings.

    With `should_apply_excludes`, the config's `exclude` globs also prune a
    matching directory, so a wholly-excluded tree is never descended. A file is
    not exclude-filtered here; `expand_paths` drops an excluded file when it
    expands a directory argument. The whole-package index passes `False`, so an
    excluded file stays readable by the cross-module rules that must still
    count it.

    Only children below `root` are pruned, never `root` itself, so a run from
    inside a worktree or under a pruned name (`~/.cache/worktrees/...`) walks
    that tree rather than skipping it whole.
    """
    pyproject = find_pyproject(root)
    table = _repostyle_table(pyproject)
    gitignore = (
        _parse_gitignore(pyproject.parent / ".gitignore")
        if pyproject is not None and _bool_config(table, "respect-gitignore")
        else _parse_gitignore(None)
    )
    exclude_table = table if should_apply_excludes else {}
    for dirpath, dirnames, filenames in os.walk(root):
        parent = Path(dirpath)
        dirnames[:] = [
            name
            for name in dirnames
            if not _is_pruned_dir(parent / name, pyproject, exclude_table, gitignore)
        ]
        for name in filenames:
            path = parent / name
            if path.suffix in suffixes and path.is_file():
                yield path


def _is_pruned_dir(
    directory: Path,
    pyproject: Path | None,
    table: dict[str, object],
    gitignore: _GitignoreRules,
) -> bool:
    """Reports whether a directory's subtree is pruned from a walk.

    A `_SKIPPED_DIRS` name or a nested repository checkout is always pruned.
    Otherwise the directory is pruned when the config's `exclude` globs match
    its whole subtree, or when the repo's `.gitignore` names it and
    `respect-gitignore` is set. An empty `table` (the whole-package walk, which
    does not apply excludes) matches no `exclude` glob, but the `.gitignore`
    prune still applies there -- a gitignored tree is not part of the repo for
    any rule, including the cross-module index.
    """
    name = directory.name
    if name in _SKIPPED_DIRS or _is_nested_checkout(directory):
        return True
    if _dir_matches_config_glob(directory, pyproject, table, "exclude"):
        return True
    return _gitignore_prunes_dir(directory, pyproject, gitignore)


def _is_nested_checkout(directory: Path) -> bool:
    """Reports whether a directory holds a separate repository's working tree.

    A `.git` entry marks the root of a checkout -- a directory in a clone, a
    file in a linked worktree. That tree is another project rather than part of
    this one, so the walk stops at its root. A `git worktree` under `.claude/`
    is a whole second copy of the repo, and reading one both dominates the
    package scan and silences RS029: the copy of a module counts as a second
    module referencing every name the original defines.
    """
    return (directory / ".git").exists()


def fix_path(path: Path, enabled: set[str]) -> bool:
    """Applies each enabled fixable rule to `path` in place, reporting change.

    A no-op unless a fixable rule is enabled and `path` is a Python, markdown,
    TOML, YAML, or shell file. The fixers run in `_FIXERS` order, each handed
    the output of the last; a comment fixer reaches every language the matching
    check reads, while a docstring fixer acts on Python alone. A whole-file
    ignore directive leaves the file untouched for that rule, and a per-line
    suppression leaves its line untouched.
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
