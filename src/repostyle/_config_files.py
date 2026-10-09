"""Finds a repository's repostyle config file and reads its settings.

The settings live in a `repostyle.toml` at its top level, or under
`[tool.repostyle]` in a `pyproject.toml`, so a repository with no Python
packaging -- a Java service, say -- configures the linter the same way.
"""

from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path


def find_config_file(start: Path) -> Path | None:
    """Walks up from `start` to the nearest repostyle config file.

    The file is a `repostyle.toml` or a `pyproject.toml`, and its directory is
    the repository root that baselines and package-wide scans are relative to.
    """
    start = start.resolve()
    return _find_config_file_from(start if start.is_dir() else start.parent)


@lru_cache(maxsize=128)
def _find_config_file_from(directory: Path) -> Path | None:
    """Walks up from `directory` to the nearest repostyle config file.

    A directory holding both files answers with `repostyle.toml`, the file that
    exists only to configure this linter.

    Caches on the directory rather than the file so a directory scan walks up
    once for all its files, not once per file across path expansion and every
    rule.
    """
    for candidate in (directory, *directory.parents):
        for name in CONFIG_FILE_NAMES:
            config = candidate / name
            if config.is_file():
                return config
    return None


CONFIG_FILE_NAMES = ("repostyle.toml", "pyproject.toml")


@lru_cache(maxsize=128)
def _repostyle_table(pyproject: Path | None) -> dict[str, object]:
    """Reads the repostyle settings from a config file, if any.

    A `repostyle.toml` holds them at its top level; a `pyproject.toml` holds
    them under `[tool.repostyle]`. A missing, unreadable, or settings-free file
    reads as an empty table.
    """
    return config_table(pyproject) or {}


def config_table(config: Path | None) -> dict[str, object] | None:
    """Returns the repostyle settings in a config file, or `None` for none."""
    if config is None:
        return None
    try:
        data = tomllib.loads(config.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    if config.name == "repostyle.toml":
        return data
    table = data.get("tool", {}).get("repostyle")
    return table if isinstance(table, dict) else None
