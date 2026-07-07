"""Console-script entry point invoked by the pre-commit hook."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from repostyle.changed_lines import changed_lines
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
    resolve_enabled_rules_for_paths,
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


def _run_lint(argv: list[str]) -> int:
    """Resolves the rule set, optionally fixes, and reports each path.

    A directory argument is expanded to the lintable files beneath it before
    reporting, so a directory recurses instead of silently linting nothing.
    Config discovery and the whole-package scan root are resolved from the
    original arguments rather than the expanded file list, so a directory
    argument still finds the `pyproject.toml` and package root it pointed at
    instead of one belonging to an arbitrary file inside it. A path that does
    not exist is reported rather than silently producing zero findings.
    """
    options = _parse_args(argv)
    missing = [path for path in options.paths if not path.exists()]
    if missing:
        listed = ", ".join(str(path) for path in missing)
        print(f"repostyle: no such path: {listed}", file=sys.stderr)
        return 2
    original_paths = options.paths
    paths = expand_paths(original_paths)
    try:
        enabled = resolve_enabled_rules_for_paths(original_paths)
    except ValueError as error:
        print(f"repostyle: {error}", file=sys.stderr)
        return 2
    package = lint_package(paths, enabled, root_paths=original_paths)
    failed = False
    fixed: list[Path] = []
    fired: set[str] = set()
    for path in paths:
        if options.fix and fix_path(path, enabled):
            fixed.append(path)
        extra = package.get(path.resolve(), [])
        path_failed, path_rules = _report_path(path, enabled, options, extra)
        failed = path_failed or failed
        fired |= path_rules
    if fixed:
        listed = ", ".join(str(path) for path in fixed)
        print(f"repostyle: fixed {listed}; review and re-stage", file=sys.stderr)
    if not options.no_explain_hint:
        for rule_id in sorted(rule for rule in fired if has_guidance(rule)):
            print(discovery_hint(rule_id), file=sys.stderr)
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
        default="HEAD",
        metavar="REF",
        help="the git ref --diff compares against (default HEAD)",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="fix fixable findings (RS005, RS009, RS030) in place before reporting",
    )
    parser.add_argument(
        "--no-explain-hint",
        action="store_true",
        help="suppress the per-rule 'run explain' pointer printed on findings",
    )
    return parser.parse_args(argv)


def _report_path(
    path: Path,
    enabled: set[str],
    options: argparse.Namespace,
    extra: list[Violation],
) -> tuple[bool, set[str]]:
    """Prints a path's findings, returning pass/fail and the rules that fired.

    `extra` carries whole-package findings already scoped to this path, merged
    with the per-file findings before diff-filtering and printing. The returned
    rule set is the rules that produced a finding on this path.
    """
    violations = sorted(set(lint_path(path, enabled)) | set(extra))
    if options.diff:
        touched = changed_lines(path, options.diff_base)
        if touched is not None:
            violations = [v for v in violations if v.line in touched]
    failed = False
    fired: set[str] = set()
    for line, col, rule, message in violations:
        severity = severity_of(rule)
        print(f"{path}:{line}:{col}: {severity.value}: {rule} {message}")
        failed = failed or severity is Severity.ERROR
        fired.add(rule)
    return failed, fired


if __name__ == "__main__":
    sys.exit(main())
