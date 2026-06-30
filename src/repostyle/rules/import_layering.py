"""Layering rule: a file may not import a source its layer forbids.

The bans are config-driven, so each repo expresses its own layering boundaries
instead of the rule hardcoding one; with no configured table the rule reports
nothing.
"""

from __future__ import annotations

import ast
import tomllib
from collections.abc import Iterator
from fnmatch import fnmatch
from functools import lru_cache
from pathlib import Path

from repostyle.rules._shared import _parse_python, _posix, find_pyproject
from repostyle.rules._violation import RS_BANNED_IMPORT_BY_PATH, Violation


def check_banned_import_by_path(path: Path, source: str) -> Iterator[Violation]:
    """A file may not import a source its layer's config forbids.

    A relative import is left to the no-relative-imports rule; only absolute
    imports are matched against the banned sources configured for a glob the
    file's path falls under.
    """
    pyproject = find_pyproject(path)
    if pyproject is None:
        return
    try:
        relative = _posix(path.resolve().relative_to(pyproject.parent))
    except ValueError:
        relative = _posix(path)
    banned: set[str] = set()
    for glob, sources in _banned_imports(pyproject):
        if fnmatch(relative, glob):
            banned |= sources
    if not banned:
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in ast.walk(tree):
        for name in _imported_sources(node):
            if _is_banned(name, banned):
                yield Violation(
                    node.lineno,
                    node.col_offset + 1,
                    RS_BANNED_IMPORT_BY_PATH,
                    f"import of '{name}' is banned for this path; it crosses a "
                    f"layering boundary the repo's config forbids",
                )


@lru_cache(maxsize=128)
def _banned_imports(pyproject: Path) -> tuple[tuple[str, frozenset[str]], ...]:
    """Read the `banned-imports` glob-to-sources table from a pyproject file."""
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return ()
    table = data.get("tool", {}).get("repostyle", {}).get("banned-imports", {})
    return tuple((glob, frozenset(sources)) for glob, sources in table.items())


def _imported_sources(node: ast.AST) -> Iterator[str]:
    """Yield the absolute module names an import statement names."""
    if isinstance(node, ast.Import):
        for alias in node.names:
            yield alias.name
    elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
        yield node.module


def _is_banned(name: str, banned: frozenset[str]) -> bool:
    """Report whether dotted module `name` is a banned source or under one."""
    return any(name == source or name.startswith(f"{source}.") for source in banned)
