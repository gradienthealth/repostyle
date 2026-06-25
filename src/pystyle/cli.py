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


def main(argv: list[str] | None = None) -> int:
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


if __name__ == "__main__":
    sys.exit(main())
