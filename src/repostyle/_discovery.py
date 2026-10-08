"""Discovers lintable files while pruning non-project trees."""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator
from pathlib import Path

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
from repostyle.languages import LINTABLE_SUFFIXES

# Directories never holding first-party source, pruned during traversal when
# building the whole-package index a package rule scans and when expanding a
# directory argument into its lintable files. The dot-prefixed names are
# version-control metadata and the caches and virtualenvs a working tree
# accumulates. Every other dot-directory is walked, because a repo keeps linted
# files in one: pre-commit hands this linter the workflow YAML under `.github`
# and the markdown under `.claude`, and a walk that skipped them would put a
# finding the gate reports beyond the reach of `--update-baseline`, which can
# only grandfather what it walks. A checkout nested under one of those -- an
# agent worktree under `.claude/` -- is pruned by `_is_nested_checkout`, which
# tests for a `.git` entry rather than matching a name.
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
    CPU-bound. A dot-prefixed file matching `suffixes` is walked like any
    other, so a repo's `.pre-commit-config.yaml` is linted where it sits.

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
    inside a worktree or under a pruned directory walks that tree rather than
    skipping it whole.
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
    this one, so the walk stops at its root. Indexing a second copy of this
    repo would also silence RS029, since the copy of a module counts as a
    second module referencing every name the original defines.
    """
    return (directory / ".git").exists()
