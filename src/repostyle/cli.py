"""Console-script entry point invoked by the pre-commit hook."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import NamedTuple

from repostyle import baseline as baseline_file
from repostyle._shared import find_pyproject
from repostyle.baseline import DEFAULT_BASELINE_NAME, Baseline
from repostyle.changed_lines import changed_lines, resolve_diff_base
from repostyle.explain import discovery_hint, explain_rule
from repostyle.rules import (
    ALL_RULE_IDS,
    Severity,
    Violation,
    has_guidance,
    severity_of,
)
from repostyle.runner import (
    expand_paths,
    fix_path,
    lint_package,
    lint_path,
    repo_root,
    resolve_baseline_path,
    resolve_rules_for_paths,
)


def main(argv: list[str] | None = None) -> int:
    """Lints the given paths, or explains a rule, and returns the exit code.

    Dispatches to the `explain` subcommand when it leads the arguments;
    otherwise lints. Linting returns 2 when a path does not exist or the rule
    set cannot be resolved, 1 when an error-severity finding remains or a file
    was fixed, and 0 otherwise. `explain` returns 2 for an unknown id and 0
    otherwise.
    """
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] == "explain":
        return _run_explain(args[1:])
    return _run_lint(args)


def _run_explain(argv: list[str]) -> int:
    """Prints the explanation card for each named rule, or every rule.

    Returns 2 when any named id is unknown, after printing the cards for the
    ids that resolve.
    """
    parser = argparse.ArgumentParser(prog="repostyle explain")
    parser.add_argument("rules", nargs="*", metavar="RSnnn")
    parser.add_argument("--all", action="store_true", help="print every rule's card")
    options = parser.parse_args(argv)
    if options.all:
        rule_ids = sorted(ALL_RULE_IDS)
    elif options.rules:
        rule_ids = options.rules
    else:
        parser.error("specify a rule id (e.g. RS010) or --all")
    cards: list[str] = []
    unknown: list[str] = []
    for rule_id in rule_ids:
        card = explain_rule(rule_id)
        if card is None:
            unknown.append(rule_id)
        else:
            cards.append(card)
    if cards:
        print("\n\n".join(cards))
    for rule_id in unknown:
        print(f"repostyle: unknown rule id {rule_id}", file=sys.stderr)
    return 2 if unknown else 0


# Printed when `--diff` cannot resolve the commit to compare against. The run
# refuses rather than reporting every line: under the error-by-default severity
# that would fail the build on the whole grandfathered tree, which reads as a
# linter outage rather than as the misconfiguration it is.
_UNRESOLVED_BASE = (
    "repostyle: --diff cannot resolve {ref}; fetch the default branch "
    "(actions/checkout with fetch-depth: 0), name a ref with --diff-base, or "
    "drop --diff to lint whole files"
)


class _PathReport(NamedTuple):
    """What reporting one path produced.

    `tolerated` counts the findings that printed as warnings, so the caller can
    say how much the run let through.
    """

    has_failure: bool
    fired: set[str]
    tolerated: int


class _Reporting(NamedTuple):
    """Everything reporting a path needs beyond the path and its findings.

    `promoted` holds the ids that print and fail as errors whatever their
    default severity. `diff_base` is the commit `--diff` compares against, or
    `None` when the run is not diff-scoped. `grandfathered` is the loaded
    baseline, or `None` when the repo has none. `root` is the directory the
    baseline's keys are relative to.
    """

    promoted: set[str]
    diff_base: str | None
    grandfathered: Baseline | None
    root: Path


class _Scope(NamedTuple):
    """The files a run covers and the rules it runs over them.

    `roots` is the arguments as given, which config discovery and the
    whole-package scan use; `paths` is those arguments with each directory
    expanded to the lintable files beneath it.
    """

    roots: list[Path]
    paths: list[Path]
    enabled: set[str]
    promoted: set[str]


def _run_lint(argv: list[str]) -> int:
    """Resolves the rule set, optionally fixes, and reports each path.

    A directory argument is expanded to the lintable files beneath it before
    reporting, so a directory recurses instead of silently linting nothing.
    Config discovery and the whole-package scan root are resolved from the
    original arguments rather than the expanded file list, so a directory
    argument still finds the `pyproject.toml` and package root it pointed at
    instead of one belonging to an arbitrary file inside it.
    """
    options = _parse_args(argv)
    scope = _resolve_scope(options)
    if scope is None:
        return 2
    package = lint_package(scope.paths, scope.enabled, root_paths=scope.roots)
    if options.write_baseline or options.update_baseline:
        return _write_baseline(options, scope, package)
    reporting = _resolve_reporting(options, scope)
    if reporting is None:
        return 2
    failed = False
    fixed: list[Path] = []
    fired: set[str] = set()
    tolerated = 0
    for path in scope.paths:
        if options.fix and fix_path(path, scope.enabled):
            fixed.append(path)
        extra = package.get(path.resolve(), [])
        report = _report_path(path, scope.enabled, reporting, extra)
        failed = report.has_failure or failed
        fired |= report.fired
        tolerated += report.tolerated
    _print_run_summary(options, fixed, fired, tolerated)
    return 1 if failed or fixed else 0


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="repostyle")
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument(
        "--diff",
        action="store_true",
        help="report only findings on lines changed versus --diff-base",
    )
    parser.add_argument(
        "--diff-base",
        default=None,
        metavar="REF",
        help="the ref --diff compares against (default: the merge-base with "
        "the repo's default branch)",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="fix the mechanically-fixable findings in place before reporting",
    )
    parser.add_argument(
        "--warnings-as-errors",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="fail on every finding, whatever its default severity (default: "
        "on; --no-warnings-as-errors restores the per-rule severities)",
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="record the tree's current findings as grandfathered and exit",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="refresh the baseline: drop findings since fixed, admit only the "
        "backlog of rules the baseline predates, and exit",
    )
    parser.add_argument(
        "--no-baseline",
        action="store_true",
        help="report every finding, ignoring the repo's baseline",
    )
    parser.add_argument(
        "--no-explain-hint",
        action="store_true",
        help="suppress the per-rule 'run explain' pointer printed on findings",
    )
    return parser.parse_args(argv)


def _print_run_summary(
    options: argparse.Namespace,
    fixed: list[Path],
    fired: set[str],
    tolerated: int,
) -> None:
    """Prints what the run rewrote, let through, and can explain, to stderr."""
    if fixed:
        listed = ", ".join(str(path) for path in fixed)
        print(f"repostyle: fixed {listed}; review and re-stage", file=sys.stderr)
    if tolerated:
        print(
            f"repostyle: {tolerated} warning(s) reported without failing the "
            "run; drop `[tool.repostyle] warnings-as-errors = false` to gate "
            "on them",
            file=sys.stderr,
        )
    if options.no_explain_hint:
        return
    for rule_id in sorted(rule for rule in fired if has_guidance(rule)):
        print(discovery_hint(rule_id), file=sys.stderr)


def _report_path(
    path: Path, enabled: set[str], reporting: _Reporting, extra: list[Violation]
) -> _PathReport:
    """Prints a path's findings and reports what they came to.

    `extra` carries whole-package findings already scoped to this path, merged
    with the per-file findings before the diff and baseline filters run. A rule
    in `reporting.promoted` prints and fails as an error whatever its default
    severity.
    """
    violations = sorted(set(lint_path(path, enabled)) | set(extra))
    if reporting.diff_base is not None:
        touched = changed_lines(path, reporting.diff_base)
        if touched is not None:
            violations = [v for v in violations if v.line in touched]
    if reporting.grandfathered is not None:
        violations = baseline_file.filter_baselined(
            path, violations, reporting.grandfathered, reporting.root
        )
    failed = False
    fired: set[str] = set()
    tolerated = 0
    for line, col, rule, message in violations:
        severity = Severity.ERROR if rule in reporting.promoted else severity_of(rule)
        print(f"{path}:{line}:{col}: {severity.value}: {rule} {message}")
        failed = failed or severity is Severity.ERROR
        tolerated += severity is Severity.WARNING
        fired.add(rule)
    return _PathReport(failed, fired, tolerated)


def _resolve_reporting(options: argparse.Namespace, scope: _Scope) -> _Reporting | None:
    """Resolves the diff base and baseline a reporting pass needs.

    Returns `None` after explaining the problem on stderr when `--diff` was
    asked for and no base commit resolves, so the caller can exit rather than
    report against a scope it could not establish.
    """
    diff_base = None
    if options.diff:
        start = scope.roots[0] if scope.roots else Path.cwd()
        diff_base = resolve_diff_base(start, options.diff_base)
        if diff_base is None:
            named = options.diff_base or "the default branch"
            print(_UNRESOLVED_BASE.format(ref=named), file=sys.stderr)
            return None
    return _Reporting(
        promoted=scope.promoted,
        diff_base=diff_base,
        grandfathered=_load_baseline(options, scope.roots),
        root=repo_root(scope.roots),
    )


def _load_baseline(options: argparse.Namespace, roots: list[Path]) -> Baseline | None:
    """Reads the repo's baseline, or `None` when there is none to apply."""
    if options.no_baseline:
        return None
    path = resolve_baseline_path(roots)
    if path is None or not path.is_file():
        return None
    loaded = baseline_file.load(path)
    if loaded is None:
        print(
            f"repostyle: ignoring unreadable baseline {path}; regenerate it "
            "with --write-baseline",
            file=sys.stderr,
        )
    return loaded


def _resolve_scope(options: argparse.Namespace) -> _Scope | None:
    """Resolves the files to lint and the rules to lint them with.

    Returns `None` after reporting the problem on stderr when a path argument
    does not exist or the config names an unknown rule id, so neither is
    mistaken for a clean run. Writing a baseline with no path argument scans
    the working directory, since a baseline covers a tree rather than a file
    list.
    """
    missing = [path for path in options.paths if not path.exists()]
    if missing:
        listed = ", ".join(str(path) for path in missing)
        print(f"repostyle: no such path: {listed}", file=sys.stderr)
        return None
    writing = options.write_baseline or options.update_baseline
    roots = options.paths or ([Path.cwd()] if writing else [])
    try:
        enabled, promoted = resolve_rules_for_paths(roots)
    except ValueError as error:
        print(f"repostyle: {error}", file=sys.stderr)
        return None
    if options.warnings_as_errors is not None:
        promoted = set(ALL_RULE_IDS) if options.warnings_as_errors else set()
    return _Scope(
        roots=roots, paths=expand_paths(roots), enabled=enabled, promoted=promoted
    )


def _write_baseline(
    options: argparse.Namespace,
    scope: _Scope,
    package: dict[Path, list[Violation]],
) -> int:
    """Records the scanned tree's findings as grandfathered and reports where.

    Returns 2 when there is no `pyproject.toml` to anchor the file to, since a
    baseline whose keys are relative to a guessed root would not match the keys
    a later run computes.
    """
    path = resolve_baseline_path(scope.roots) or _default_baseline_path(scope.roots)
    if path is None:
        print(
            "repostyle: no pyproject.toml found, so there is nowhere to anchor "
            "a baseline; run from inside the repo",
            file=sys.stderr,
        )
        return 2
    root = repo_root(scope.roots)
    findings = {
        scanned: sorted(
            set(lint_path(scanned, scope.enabled))
            | set(package.get(scanned.resolve(), []))
        )
        for scanned in scope.paths
    }
    current = baseline_file.build(findings, root, frozenset(scope.enabled))
    existing = baseline_file.load(path) if path.is_file() else None
    written = (
        baseline_file.refresh(existing, current)
        if options.update_baseline and existing is not None
        else current
    )
    baseline_file.save(path, written)
    total = sum(
        count for per_rule in written.counts.values() for count in per_rule.values()
    )
    print(
        f"repostyle: wrote {path} grandfathering {total} finding(s) across "
        f"{len(written.counts)} file(s)",
        file=sys.stderr,
    )
    return 0


def _default_baseline_path(roots: list[Path]) -> Path | None:
    """Returns where a first baseline goes: beside the pyproject file."""
    if not roots:
        return None
    pyproject = find_pyproject(roots[0])
    return None if pyproject is None else pyproject.parent / DEFAULT_BASELINE_NAME


if __name__ == "__main__":
    sys.exit(main())
