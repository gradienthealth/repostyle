"""Console-script entry point invoked by the pre-commit hook."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from gradient_pystyle.changed_lines import changed_lines
from gradient_pystyle.rules import Severity, severity_of
from gradient_pystyle.runner import lint_path, resolve_enabled_rules_for_paths


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="gradient-pystyle")
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
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    options = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        enabled = resolve_enabled_rules_for_paths(options.paths)
    except ValueError as error:
        print(f"gradient-pystyle: {error}", file=sys.stderr)
        return 2
    failed = False
    for path in options.paths:
        violations = lint_path(path, enabled)
        if options.diff:
            touched = changed_lines(path, options.diff_base)
            if touched is not None:
                violations = [v for v in violations if v.line in touched]
        for line, col, rule, message in violations:
            severity = severity_of(rule)
            print(f"{path}:{line}:{col}: {severity.value}: {rule} {message}")
            failed = failed or severity is Severity.ERROR
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
