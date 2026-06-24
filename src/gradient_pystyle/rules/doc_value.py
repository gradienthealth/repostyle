"""Documentation-value signal (RS018): warn where a docstring earns its keep.

Score a function's documentation value from its cognitive complexity and
signature, and warn only when a non-trivial public function is
under-documented, so trivial one-liners stay silent. The warning reads as
"documentation would help here," distinct from a binary "missing
docstring" error.

The signal has three triggers. The presence trigger fires when a complex
or many-argumented public function carries no docstring. The `Args:`
trigger fires when a documented public function has many parameters but
no structured `Args:` section. The `Returns:` trigger fires when a
documented function returns a multi-element `tuple` — an anonymous
composite whose parts a single summary line cannot name; a scalar, a
named type, or a homogeneous collection is left to the summary line.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

from gradient_pystyle.rules._shared import _is_test_file, _parse_python
from gradient_pystyle.rules._violation import RS_DOC_VALUE_SIGNAL, Violation
from gradient_pystyle.rules.complexity import _score_block

# The presence check fires when a function scores at or above the
# complexity floor (well below RS012's limit of 15, which marks
# over-complexity, not mere worth-documenting) or has at least the
# parameter floor. The `Args:` trigger keeps its own parameter floor.
DOC_VALUE_COMPLEXITY_FLOOR = 5
DOC_VALUE_PARAM_FLOOR = 4
DOC_VALUE_ARGS_PARAM_FLOOR = 4

_ARGS_SECTION_PATTERN = re.compile(r"^[ \t]*(Args|Arguments):\s*$", re.MULTILINE)
_RETURNS_SECTION_PATTERN = re.compile(r"^[ \t]*(Returns|Yields):\s*$", re.MULTILINE)


def _param_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Count a function's parameters, excluding a leading `self`/`cls`."""
    args = node.args
    positional = args.posonlyargs + args.args
    count = len(positional) + len(args.kwonlyargs)
    if args.vararg is not None:
        count += 1
    if args.kwarg is not None:
        count += 1
    if positional and positional[0].arg in ("self", "cls"):
        count -= 1
    return count


def _returns_multi_element_tuple(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Report whether the return annotation is a `tuple` of named parts.

    A multi-element `tuple` is an anonymous composite whose parts a
    single summary line cannot enumerate, so it warrants a `Returns:`
    section. The variadic `tuple[X, ...]` form is a homogeneous
    sequence, not a composite, and is excluded.
    """
    annotation = node.returns
    if not isinstance(annotation, ast.Subscript):
        return False
    base = annotation.value
    name = base.id if isinstance(base, ast.Name) else getattr(base, "attr", None)
    if name not in ("tuple", "Tuple"):
        return False
    if not isinstance(annotation.slice, ast.Tuple):
        return False
    elements = annotation.slice.elts
    last = elements[-1] if elements else None
    if isinstance(last, ast.Constant) and last.value is Ellipsis:
        return False
    return len(elements) >= 2


def _has_decorator(
    node: ast.FunctionDef | ast.AsyncFunctionDef, names: set[str]
) -> bool:
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Name) and target.id in names:
            return True
        if isinstance(target, ast.Attribute) and target.attr in names:
            return True
    return False


def _violation(node: ast.FunctionDef | ast.AsyncFunctionDef, message: str) -> Violation:
    return Violation(node.lineno, node.col_offset + 1, RS_DOC_VALUE_SIGNAL, message)


def _check_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> Iterator[Violation]:
    docstring = ast.get_docstring(node, clean=False)
    params = _param_count(node)
    if docstring is None:
        score = _score_block(node.body, 0)
        if score >= DOC_VALUE_COMPLEXITY_FLOOR or params >= DOC_VALUE_PARAM_FLOOR:
            plural = "" if params == 1 else "s"
            yield _violation(
                node,
                f"function '{node.name}' is non-trivial (cognitive complexity "
                f"{score}, {params} parameter{plural}) but has no docstring; "
                "document it",
            )
        return
    if params >= DOC_VALUE_ARGS_PARAM_FLOOR and not _ARGS_SECTION_PATTERN.search(
        docstring
    ):
        yield _violation(
            node,
            f"function '{node.name}' has {params} parameters but its docstring "
            "has no `Args:` section; document them in one rather than in prose",
        )
    if _returns_multi_element_tuple(node) and not _RETURNS_SECTION_PATTERN.search(
        docstring
    ):
        yield _violation(
            node,
            f"function '{node.name}' returns a multi-element tuple but its "
            "docstring has no `Returns:` section; name the elements",
        )


def check_doc_value_signal(path: Path, source: str) -> Iterator[Violation]:
    """Warn when a non-trivial public function is under-documented.

    A public function with no docstring earns a warning when it is
    complex or many-argumented; a documented public function earns one
    when it has many parameters but no `Args:` section, or returns a
    multi-element `tuple` but no `Returns:` section. Trivial, non-public,
    test, and `@overload` definitions never fire.
    """
    if _is_test_file(path):
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if node.name.startswith(("_", "test_")):
            continue
        if _has_decorator(node, {"overload"}):
            continue
        yield from _check_function(node)
