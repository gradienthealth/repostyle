"""Console-script entry point invoked by the pre-commit hook."""

from __future__ import annotations

import sys
from pathlib import Path

from gradient_pystyle.runner import lint_path, resolve_enabled_rules_for_paths


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    paths = [Path(arg) for arg in args]
    try:
        enabled = resolve_enabled_rules_for_paths(paths)
    except ValueError as error:
        print(f"gradient-pystyle: {error}", file=sys.stderr)
        return 2
    found = False
    for path in paths:
        for line, col, rule, message in lint_path(path, enabled):
            print(f"{path}:{line}:{col}: {rule} {message}")
            found = True
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
