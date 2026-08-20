"""Idiom rules: a Pythonic construct is preferred over a literal-minded one.

The home for rules that flag a working but un-Pythonic shape whose fluent form
reads better. RS046 catches the canonical case -- a `for` loop over
`range(len(seq))` that uses the index only to subscript that same sequence,
where direct iteration (`for item in seq:`) says the same thing without the
index. The check is scoped tightly so an index genuinely needed for arithmetic,
a second sequence, or a call never fires; it does not reach for the weaker
`enumerate` suggestion, to keep its false-positive rate near zero.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

from repostyle._shared import _parse_python, _walk_tree
from repostyle.rules._violation import RS_RANGE_LEN_REINDEX, Violation


def check_range_len_reindex(path: Path, source: str) -> Iterator[Violation]:
    """Flags a `for i in range(len(seq))` that indexes only `seq[i]`.

    The un-Pythonic re-index loops over the integers of `range(len(seq))` only
    to subscript the same sequence at each one, where `for item in seq:` reads
    the elements directly. The check fires only when the loop `iter` is a
    `range(len(x))` call over a single argument, its target is a lone index
    name, and every use of that name in the body is a subscript `x[i]` of that
    same sequence -- `x` matched structurally, so a plain name or an attribute
    like `self.rows` both work. An index used bare anywhere else (passed to a
    call, used in arithmetic, indexing a second sequence) means the index is
    genuinely needed, so the loop is left alone rather than steered toward the
    weaker `enumerate` form this rule deliberately does not suggest. Both `for`
    and `async for` are covered.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in _walk_tree(tree):
        if isinstance(node, ast.For | ast.AsyncFor):
            yield from _reindex_violation(node)


def _reindex_violation(node: ast.For | ast.AsyncFor) -> Iterator[Violation]:
    """Yields the re-index violation a loop earns, if it fits the shape."""
    sequence = _range_len_argument(node.iter)
    if sequence is None or not isinstance(node.target, ast.Name):
        return
    index = node.target.id
    uses = [name for stmt in node.body for name in _index_names(stmt, index)]
    indexed = [
        sub for stmt in node.body for sub in _reindex_subscripts(stmt, index, sequence)
    ]
    if indexed and len(uses) == len(indexed):
        rendered = ast.unparse(sequence)
        yield Violation(
            node.lineno,
            node.col_offset + 1,
            RS_RANGE_LEN_REINDEX,
            f"loops over `range(len({rendered}))` only to index `{rendered}`; "
            f"iterate `{rendered}` directly",
        )


def _index_names(node: ast.AST, index: str) -> Iterator[ast.Name]:
    """Yields every `Name` node in a subtree referring to the index name."""
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id == index:
            yield child


def _range_len_argument(iter_node: ast.expr) -> ast.expr | None:
    """Returns the `x` of a `range(len(x))` iterator, or `None`.

    The iterator qualifies only as a bare `range(...)` call over a single
    positional argument that is itself a bare `len(...)` call over a single
    positional argument, and that inner argument -- a `Name` or an `Attribute`
    -- is returned as the sequence. Any keyword, star, or extra positional
    argument on either call disqualifies the loop.
    """
    if not _is_single_arg_call(iter_node, "range"):
        return None
    assert isinstance(iter_node, ast.Call)
    length = iter_node.args[0]
    if not _is_single_arg_call(length, "len"):
        return None
    assert isinstance(length, ast.Call)
    sequence = length.args[0]
    if isinstance(sequence, ast.Name | ast.Attribute):
        return sequence
    return None


def _is_single_arg_call(node: ast.expr, name: str) -> bool:
    """Reports whether `node` is a bare `name(arg)` call with one argument."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == name
        and len(node.args) == 1
        and not node.keywords
        and not any(isinstance(arg, ast.Starred) for arg in node.args)
    )


def _reindex_subscripts(
    node: ast.AST, index: str, sequence: ast.expr
) -> Iterator[ast.Subscript]:
    """Yields each `sequence[index]` subscript found in a subtree.

    A subscript qualifies only when its slice is the bare index name and its
    value matches the loop's sequence structurally, so a subscript of a second
    sequence or one whose slice is an expression like `index + 1` is excluded
    -- leaving the caller a use of the index that the direct-iteration rewrite
    could not carry.
    """
    for child in ast.walk(node):
        if (
            isinstance(child, ast.Subscript)
            and isinstance(child.slice, ast.Name)
            and child.slice.id == index
            and _same_structure(child.value, sequence)
        ):
            yield child


def _same_structure(left: ast.expr, right: ast.expr) -> bool:
    """Reports whether two expressions share a structure, ignoring position."""
    return ast.dump(left) == ast.dump(right)
