"""Cognitive-complexity rule: warn when a function is too hard to follow.

Cognitive complexity weights control flow by how deeply it nests, so a
flat sequence of branches scores far lower than the same branches buried
inside each other. The limit of 15 is Sonar's default rule threshold,
not a figure from Campbell's original paper, so the warning marks a
function worth a second look rather than asserting a defect.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

from gradient_pystyle.rules._shared import _parse_python
from gradient_pystyle.rules._violation import RS_COGNITIVE_COMPLEXITY, Violation

COGNITIVE_COMPLEXITY_LIMIT = 15

_NESTING_STRUCTURES = (ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler, ast.IfExp)
_NESTING_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def _score_block(body: list[ast.stmt], nesting: int) -> int:
    return sum(_score_node(node, nesting) for node in body)


def _score_node(node: ast.AST, nesting: int) -> int:
    """Return the nesting-weighted cost of one node and its descendants."""
    if isinstance(node, ast.If):
        return _score_if(node, nesting)
    if isinstance(node, _NESTING_STRUCTURES):
        return 1 + nesting + _score_children(node, nesting + 1)
    if isinstance(node, ast.BoolOp):
        return 1 + _score_children(node, nesting)
    if isinstance(node, _NESTING_SCOPES):
        return _score_children(node, nesting + 1)
    return _score_children(node, nesting)


def _score_children(node: ast.AST, nesting: int) -> int:
    return sum(_score_node(child, nesting) for child in ast.iter_child_nodes(node))


def _score_if(node: ast.If, nesting: int) -> int:
    """Score an `if`, treating an `elif` as a flat continuation, not deeper nesting.

    An `elif` is a lone `If` in the `orelse`; scoring it at the same
    nesting keeps a dispatch chain of branches from reading as deeply
    nested code, matching how cognitive complexity treats `else if`.
    """
    score = 1 + nesting + _score_node(node.test, nesting)
    score += _score_block(node.body, nesting + 1)
    if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
        score += _score_if(node.orelse[0], nesting)
    else:
        score += _score_block(node.orelse, nesting + 1)
    return score


def check_cognitive_complexity(path: Path, source: str) -> Iterator[Violation]:
    """Flag a function whose cognitive complexity exceeds the limit.

    Each branch (`if`, `for`, `while`, `except`, conditional expression)
    and each boolean-operator sequence adds to the score, and a branch
    nested inside another adds more for its depth. A function scoring
    over the limit is reported at its `def` line as a warning.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        score = _score_block(node.body, 0)
        if score > COGNITIVE_COMPLEXITY_LIMIT:
            yield Violation(
                node.lineno,
                node.col_offset + 1,
                RS_COGNITIVE_COMPLEXITY,
                f"function '{node.name}' has cognitive complexity {score}; over "
                f"the limit of {COGNITIVE_COMPLEXITY_LIMIT}, consider simplifying",
            )
