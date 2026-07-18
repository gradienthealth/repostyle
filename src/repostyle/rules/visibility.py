"""Visibility rule: a public name used only in its module should be private.

Unlike every other rule, this one reasons across the whole package: it catalogs
each module's top-level public `def`/`class` and every module's references,
then flags a public name that is used only inside its own module and exported
nowhere. Such a name leaked public scope and should carry a leading underscore,
or be added to `__all__` if it is genuinely part of the package's public API.

The public surface a repo declares is the authoritative contract, so a name is
left alone when it appears in any `__all__`, is re-exported from a public
module (every `__init__.py`, plus any `public-modules` glob), is a
`[project.scripts]` entry point, or is named in the `public-names` /
`public-decorators` escape hatches. Cross-module reference detection errs
toward counting a use, so the rule under- rather than over-reports.
"""

from __future__ import annotations

import ast
import tomllib
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from fnmatch import fnmatch
from functools import lru_cache
from pathlib import Path

from repostyle._shared import _parse_python, _posix, find_pyproject
from repostyle.rules._violation import RS_SHOULD_BE_PRIVATE, Violation


def check_should_be_private(
    files: Sequence[tuple[Path, str]],
) -> Iterator[tuple[Path, Violation]]:
    """Flags a public top-level name used only within its own module.

    A name fires only when it is loaded inside its defining module yet
    referenced by no other first-party module and absent from the declared
    public surface. A name used nowhere is dead code, not an internal-only
    name, and is left to a different tool.
    """
    modules = [
        facts
        for path, source in files
        if (facts := _module_facts(path, source)) is not None
    ]
    if not modules:
        return
    public = _public_surface(modules, files[0][0])
    decorators = _public_decorators(files[0][0])
    for module in modules:
        others = [other for other in modules if other.path != module.path]
        for name, line, col, used_decorators in module.public_defs:
            if name in public or used_decorators & decorators:
                continue
            if name not in module.name_loads:
                continue
            if any(name in other.broad_refs for other in others):
                continue
            yield (
                module.path,
                Violation(
                    line,
                    col,
                    RS_SHOULD_BE_PRIVATE,
                    f"'{name}' is public but used only within its own module; "
                    f"prefix it with '_' to mark it internal, or add it to "
                    f"__all__ if it is part of the package's public API",
                ),
            )


def _module_facts(path: Path, source: str) -> _ModuleFacts | None:
    """Distils one module's defs, exports, imports, and references."""
    tree = _parse_python(path, source)
    if tree is None:
        return None
    facts = _ModuleFacts(path=path, is_public=_is_public_module(path))
    _collect_definitions(tree, facts)
    _collect_references(tree, facts)
    facts.broad_refs |= facts.imported
    return facts


# A top-level public `def`/`class` as `(name, line, col, decorators)`
_PublicDef = tuple[str, int, int, frozenset[str]]


@dataclass
class _ModuleFacts:
    """What one module contributes to the package-wide visibility pass."""

    path: Path
    """The module's source path."""
    is_public: bool
    """Whether the module itself is a public surface that re-exports names."""
    public_defs: list[_PublicDef] = field(default_factory=list)
    """Top-level public `def`/`class` as `(name, line, col, decorators)`."""
    exported: set[str] = field(default_factory=set)
    """Names this module declares in `__all__`."""
    imported: set[str] = field(default_factory=set)
    """Names this module binds through an import (its re-export candidates)."""
    name_loads: set[str] = field(default_factory=set)
    """Identifiers this module loads by name, a precise local-use signal."""
    broad_refs: set[str] = field(default_factory=set)
    """Identifiers this module mentions, a generous cross-module signal."""


def _collect_definitions(tree: ast.AST, facts: _ModuleFacts) -> None:
    """Records top-level public defs of `tree` and its `__all__` exports."""
    for node in tree.body:
        if isinstance(
            node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
        ) and not node.name.startswith("_"):
            facts.public_defs.append(
                (
                    node.name,
                    node.lineno,
                    node.col_offset + 1,
                    _decorator_names(node),
                )
            )
        facts.exported |= _exported_names(node)


def _collect_references(tree: ast.AST, facts: _ModuleFacts) -> None:
    """Records the imports, name loads, and broad references across `tree`."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            facts.imported |= _bound_import_names(node)
        elif isinstance(node, ast.Name):
            facts.broad_refs.add(node.id)
            if isinstance(node.ctx, ast.Load):
                facts.name_loads.add(node.id)
        elif isinstance(node, ast.Attribute):
            facts.broad_refs.add(node.attr)


def _bound_import_names(node: ast.Import | ast.ImportFrom) -> set[str]:
    """Returns the names an import binds into the module namespace."""
    names: set[str] = set()
    for alias in node.names:
        if alias.name == "*":
            continue
        if alias.asname:
            names.add(alias.asname)
        elif isinstance(node, ast.ImportFrom):
            names.add(alias.name)
        else:
            names.add(alias.name.split(".")[0])
    return names


def _decorator_names(
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
) -> frozenset[str]:
    """Returns the final attribute name of each decorator on a definition."""
    names: set[str] = set()
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, ast.Attribute):
            names.add(target.attr)
    return frozenset(names)


def _exported_names(node: ast.stmt) -> set[str]:
    """Returns the string entries of a module-level `__all__` assignment."""
    targets = node.targets if isinstance(node, ast.Assign) else []
    if isinstance(node, ast.AnnAssign):
        targets = [node.target]
    if not any(isinstance(t, ast.Name) and t.id == "__all__" for t in targets):
        return set()
    value = node.value
    if not isinstance(value, ast.List | ast.Tuple):
        return set()
    return {
        element.value
        for element in value.elts
        if isinstance(element, ast.Constant) and isinstance(element.value, str)
    }


def _is_public_module(path: Path) -> bool:
    """Reports whether a module re-exports names as a public surface.

    Every package `__init__.py` is a re-export surface; a repo names any other
    export module through the `public-modules` glob list.
    """
    if path.name == "__init__.py":
        return True
    pyproject = find_pyproject(path)
    if pyproject is None:
        return False
    try:
        relative = _posix(path.resolve().relative_to(pyproject.parent))
    except ValueError:
        relative = _posix(path)
    return any(fnmatch(relative, glob) for glob in _public_modules(pyproject))


def _public_decorators(anchor: Path) -> frozenset[str]:
    """Reads the `public-decorators` allowlist from the file's pyproject."""
    pyproject = find_pyproject(anchor)
    if pyproject is None:
        return frozenset()
    return frozenset(_string_list(pyproject, "public-decorators"))


@lru_cache(maxsize=128)
def _public_modules(pyproject: Path) -> tuple[str, ...]:
    """Reads the `public-modules` glob list from a pyproject file."""
    return _string_list(pyproject, "public-modules")


def _public_surface(modules: Sequence[_ModuleFacts], anchor: Path) -> set[str]:
    """Collects every name the package declares as part of its public API."""
    public: set[str] = set(_entry_point_names(anchor)) | set(_public_names(anchor))
    for module in modules:
        public |= module.exported
        if module.is_public:
            public |= {name for name, _, _, _ in module.public_defs}
            public |= module.imported
    return public


@lru_cache(maxsize=128)
def _entry_point_names(anchor: Path) -> tuple[str, ...]:
    """Returns function names declared as `[project.scripts]` entry points."""
    pyproject = find_pyproject(anchor)
    if pyproject is None:
        return ()
    scripts = _load_pyproject(pyproject).get("project", {}).get("scripts", {})
    return tuple(
        target.rsplit(":", 1)[1].split(".", 1)[0]
        for target in scripts.values()
        if isinstance(target, str) and ":" in target
    )


def _public_names(anchor: Path | None) -> tuple[str, ...]:
    """Reads the `public-names` allowlist from the anchor's pyproject."""
    pyproject = find_pyproject(anchor) if anchor is not None else None
    return _string_list(pyproject, "public-names") if pyproject is not None else ()


@lru_cache(maxsize=128)
def _string_list(pyproject: Path, key: str) -> tuple[str, ...]:
    """Reads a `[tool.repostyle]` list-of-strings setting from `pyproject`."""
    data = _load_pyproject(pyproject)
    value = data.get("tool", {}).get("repostyle", {}).get(key, [])
    return tuple(str(entry) for entry in value) if isinstance(value, list) else ()


@lru_cache(maxsize=128)
def _load_pyproject(pyproject: Path) -> dict:
    try:
        return tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
