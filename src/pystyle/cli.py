"""Console-script entry point invoked by the pre-commit hook."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pystyle.changed_lines import changed_lines
from pystyle.rules import Severity, severity_of
from pystyle.runner import (
    fix_path,
    lint_path,
    resolve_enabled_rules_for_paths,
)


def main(argv: list[str] | None = None) -> int:
    """Lint the given paths and return the process exit code.

    Parse the arguments, resolve the enabled rule set, optionally reflow
    RS009 findings in place under `--fix`, and print each path's
    findings. Return 2 when the rule set cannot be resolved, 1 when an
    error-severity finding remains or a file was reflowed, and 0
    otherwise.
    """
    options = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        enabled = resolve_enabled_rules_for_paths(options.paths)
    except ValueError as error:
        print(f"pystyle: {error}", file=sys.stderr)
        return 2
    failed = False
    fixed: list[Path] = []
    for path in options.paths:
        if options.fix and fix_path(path, enabled):
            fixed.append(path)
        failed = _report_path(path, enabled, options) or failed
    if fixed:
        listed = ", ".join(str(path) for path in fixed)
        print(f"pystyle: reflowed {listed}; review and re-stage", file=sys.stderr)
    return 1 if failed or fixed else 0


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="pystyle")
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
        help="reflow fixable findings (RS009) in place before reporting",
    )
    return parser.parse_args(argv)


def _report_path(path: Path, enabled: set[str], options: argparse.Namespace) -> bool:
    """Print a path's findings and report whether any is error-severity."""
    violations = lint_path(path, enabled)
    if options.diff:
        touched = changed_lines(path, options.diff_base)
        if touched is not None:
            violations = [v for v in violations if v.line in touched]
    failed = False
    for line, col, rule, message in violations:
        severity = severity_of(rule)
        print(f"{path}:{line}:{col}: {severity.value}: {rule} {message}")
        failed = failed or severity is Severity.ERROR
    return failed


if __name__ == "__main__":
    sys.exit(main())
