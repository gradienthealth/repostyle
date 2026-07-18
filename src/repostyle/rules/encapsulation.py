"""Encapsulation rule: a package's internals are reached only from inside it.

A single leading underscore marks a module or name internal to the package that
contains it, so a first-party import that reaches such an internal from outside
its owning package steps over a boundary the author drew on purpose. The
sanctioned way to consume another package's functionality is the public surface
it re-exports from its `__init__`, never a reach into its `_private` members.
This is the enforcement dual of the `should-be-private` rule (RS029): that rule
asks a package to hide what only it uses, this one asks other code to respect
the hiding.

The rule scopes to imports that stay within one distribution — the target and
the importer share a top-level package — so it polices a repo's own layering
without flagging a reach into an installed third-party dependency, whose
internals are outside a repo's control. It follows PEP 8's `Public and internal
interfaces`: an interface is internal if any containing namespace is, and other
modules must not rely on indirect access to it except through a package's
documented `__init__` surface.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

from repostyle.rules._shared import _is_test_file, _parse_python
from repostyle.rules._violation import RS_PRIVATE_IMPORT, Violation


def check_private_import(path: Path, source: str) -> Iterator[Violation]:
    """Flags a first-party import that reaches a package's private internals.

    An import fires when it binds a leading-underscore module or name that
    belongs to a package the importing file does not live inside, since that
    member is internal to its own package and reachable only through the public
    surface that package re-exports. An import that stays within the owning
    package, one crossing into a third-party distribution, and one in a test
    module — where reaching a unit under test's internals is expected — are all
    left alone.
    """
    if _is_test_file(path):
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    importer = _dotted_module(path)
    importer_top = importer.split(".", 1)[0]
    for node in ast.walk(tree):
        for dotted in _candidates(node, importer_top):
            owner = _private_owner(dotted, importer_top)
            if owner is not None and not _is_inside(importer, owner):
                yield _violation(node, dotted, owner)


def _candidates(node: ast.AST, importer_top: str) -> list[str]:
    """Returns the dotted import targets a statement should be tested against.

    A private module is reported once for the whole statement; a public module
    contributes one candidate per name it imports, so a private name pulled
    from a public module is still caught.
    """
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
        if _private_owner(node.module, importer_top) is not None:
            return [node.module]
        return [f"{node.module}.{alias.name}" for alias in node.names]
    return []


def _dotted_module(path: Path) -> str:
    """Resolves a file's dotted module name from its enclosing packages.

    The name is the file's path below the highest ancestor that is still a
    package (an `__init__.py`-bearing directory), so a `src/` or other prefix
    above the top package drops away. A file in no package resolves to its bare
    stem.
    """
    resolved = path.resolve()
    packages = []
    directory = resolved.parent
    while (directory / "__init__.py").exists():
        packages.append(directory)
        directory = directory.parent
    if not packages:
        return resolved.stem
    parts = list(resolved.relative_to(packages[-1].parent).parts)
    parts[-1] = parts[-1].removesuffix(".py")
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _is_inside(importer: str, owner: str) -> bool:
    """Reports whether the importing module lives within the owning package."""
    return importer == owner or importer.startswith(f"{owner}.")


def _private_owner(dotted: str, importer_top: str) -> str | None:
    """Returns the package a first-party dotted path is internal to, if any.

    The owner is the dotted prefix before the shallowest single-underscore
    component, the point at which the path enters private scope. A path in
    another top-level distribution, one with no private component, and one
    whose private component is itself the top-level package all return `None`.
    """
    components = dotted.split(".")
    if components[0] != importer_top:
        return None
    for index, component in enumerate(components):
        if component.startswith("_") and not component.startswith("__"):
            return ".".join(components[:index]) or None
    return None


def _violation(node: ast.stmt, dotted: str, owner: str) -> Violation:
    """Builds the finding for an import of `dotted` internal to `owner`."""
    return Violation(
        node.lineno,
        node.col_offset + 1,
        RS_PRIVATE_IMPORT,
        f"import of '{dotted}' reaches into '{owner}' internals; import from "
        f"that package's public surface instead of its '_'-private members",
    )
