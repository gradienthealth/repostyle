"""Error-handling rules: a handler catches what its block genuinely raises.

The home for rules about the shape of a `try` / `except`, as distinct from
RS028 in `naming`, which governs only what a caught exception is called. RS052
is the first: an `except` tuple wide enough to take in the structural builtins
is blanketing its block rather than handling a known failure, and the fix
belongs either in the callee that should name that failure or in a `try`
narrowed to the statement the handler was written for.
"""

from __future__ import annotations

import ast
import builtins
from collections.abc import Iterable, Iterator
from pathlib import Path

from repostyle._shared import _parse_python
from repostyle.rules._violation import RS_OVER_BROAD_EXCEPT, Violation

STRUCTURAL_BUILTINS = frozenset(
    {
        "AttributeError",
        "IndexError",
        "KeyError",
        "NameError",
        "TypeError",
        "UnboundLocalError",
    }
)
"""Builtins raised when a value was not the shape the code assumed.

Each of these is what a bug looks like from the outside, which is why catching
one across a multi-statement block is indiscriminate: the handler cannot tell
the failure it was written for from a typo in the same block. `ValueError`,
`OSError`, and their kin are deliberately absent, since those report a value or
an environment the code handled correctly and does not control, so catching one
is ordinary rather than compensating.
"""

_BUILTIN_EXCEPTIONS = frozenset(
    name
    for name, value in vars(builtins).items()
    if isinstance(value, type) and issubclass(value, BaseException)
)
"""Every exception the builtins define.

A caught name outside this set is one somebody declared, in the stdlib, in a
third-party package, or in this project. Its presence in a handler therefore
shows the callee already reports that failure by name.
"""


def check_over_broad_except(path: Path, source: str) -> Iterator[Violation]:
    """Flags an `except` tuple reaching past the failure it was written for.

    A handler earns a finding two ways. Catching two or more structural
    builtins at once — `AttributeError`, `TypeError`, `KeyError`, `IndexError`,
    `NameError`, `UnboundLocalError` — means the block is being blanketed
    rather than a known failure handled, since each of those says a value was
    not the shape the code assumed. Catching one of them alongside a declared
    exception says the same thing more sharply. A declared exception is any
    name the builtins do not define, whether from the stdlib, a third-party
    package, or this project, and it is already the callee's error contract, so
    a builtin beside it is covering something else — usually a dereference
    elsewhere in the same `try`. Either shape means the callee should convert
    the failure where it arises, or the `try` covers more statements than the
    handler was written for.

    Three shapes are left alone. A handler ending in a `raise` is a boundary
    converting what it caught into one named failure, which is the fix this
    rule asks for rather than the smell it looks for. A single structural
    builtin is routinely deliberate. And a tuple of the value-and-environment
    errors (`ValueError`, `OSError`, `LookupError`, and their kin) reports
    something the code handled correctly and does not control. A bare `except
    Exception` is out of scope and belongs to ruff's `BLE001`.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            yield from _over_broad_violation(node)


def _over_broad_violation(node: ast.ExceptHandler) -> Iterator[Violation]:
    """Yields the violation a handler earns, if its tuple is too wide."""
    if not isinstance(node.type, ast.Tuple) or _is_converting(node):
        return
    caught = [name for element in node.type.elts if (name := _exception_name(element))]
    structural = _distinct_names(n for n in caught if n in STRUCTURAL_BUILTINS)
    foreign = _distinct_names(n for n in caught if n not in _BUILTIN_EXCEPTIONS)
    # Two structural builtins is the threshold, because a single one is
    # routinely deliberate: `except AttributeError` on a duck-typed probe, or
    # the `(TypeError, ValueError)` pair every `int()` conversion needs. A name
    # repeated in the tuple counts once, since ruff's `B025` owns that.
    if structural and (len(structural) > 1 or foreign):
        yield Violation(
            node.lineno,
            node.col_offset + 1,
            RS_OVER_BROAD_EXCEPT,
            _message(structural, foreign),
        )


def _distinct_names(names: Iterable[str]) -> list[str]:
    """Drops repeated names, keeping the order the `except` line reads in."""
    return list(dict.fromkeys(names))


def _exception_name(element: ast.expr) -> str | None:
    """Reads the name a tuple element catches, dropping any qualifier.

    A name that does not open with a capital is not read as an exception at
    all, matching how `doc_value` reads one. That keeps the lowercase stdlib
    aliases out of the count: `os.error` and `socket.timeout` are `OSError` and
    `TimeoutError` themselves, so counting `error` or `timeout` as a declared
    exception would contradict this rule's own exemption for those classes.

    Returns:
        `ParseError` for both `ParseError` and `errors.ParseError`, or `None`
        for an element that is not a capitalized plain reference, which is rare
        enough to leave to review.
    """
    name = None
    if isinstance(element, ast.Name):
        name = element.id
    elif isinstance(element, ast.Attribute):
        name = element.attr
    return name if name and name[0].isupper() else None


def _is_converting(node: ast.ExceptHandler) -> bool:
    """Reports whether the handler ends by raising rather than by swallowing.

    A handler whose last statement is a `raise` is the adapter boundary doing
    its job: it takes in whatever the block below can fail with and re-reports
    it as one named error, so the callers above it need catch only that. Width
    there is the point, not a defect. A handler that raises on one branch and
    falls through on another still swallows, so only the closing statement
    counts.
    """
    return isinstance(node.body[-1], ast.Raise)


def _message(structural: list[str], foreign: list[str]) -> str:
    """Renders the finding for whichever of the two shapes the handler has.

    Returns:
        The message, naming the builtins that widened the handler and, where
        there are any, the declared exceptions whose contract they reach past.
    """
    listed = ", ".join(structural)
    if foreign:
        named = ", ".join(foreign)
        return (
            f"except catches {listed} alongside {named}; {named} already names "
            f"the failure this block handles, so drop the builtins and move "
            f"what raises them out of the `try`"
        )
    return (
        f"except catches {listed} together; each says a value was not the shape "
        f"the code assumed, so raise a named error where that is decided and "
        f"narrow this handler to it"
    )
