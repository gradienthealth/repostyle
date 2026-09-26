"""Focused helpers extracted from a larger module."""

from __future__ import annotations

import argparse
from pathlib import Path


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="repostyle")
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument(
        "--diff",
        action="store_true",
        help="deprecated: report only findings on lines changed versus "
        "--diff-base; use --write-baseline instead",
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
        "off; config may promote individual rules)",
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
