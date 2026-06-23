"""Console-script entry point invoked by the pre-commit hook."""

from __future__ import annotations

import sys
from pathlib import Path

from gradient_pystyle.runner import lint_path, resolve_enabled_rules_for_paths


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    paths = [Path(arg) for arg in args]
    enabled = resolve_enabled_rules_for_paths(paths)
    found = False
    for path in paths:
        for line, rule, message in lint_path(path, enabled):
            print(f"{path}:{line}: {rule} {message}")
            found = True
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
