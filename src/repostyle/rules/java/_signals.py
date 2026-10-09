"""Java review signals: a complex method, and one left undocumented."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from repostyle.languages import (
    JAVA,
    JavaDeclaration,
    java_code_tokens,
    java_declarations,
)
from repostyle.rules._doc_value_analysis import (
    DOC_VALUE_COMPLEXITY_FLOOR,
    DOC_VALUE_PARAM_FLOOR,
)
from repostyle.rules._violation import (
    RS_COGNITIVE_COMPLEXITY,
    RS_DOC_VALUE_SIGNAL,
    Violation,
)
from repostyle.rules.complexity import COGNITIVE_COMPLEXITY_LIMIT
from repostyle.rules.java._complexity import java_cognitive_complexity


def check_java_cognitive_complexity(path: Path, source: str) -> Iterator[Violation]:
    """Flags a Java method or constructor over RS012's complexity limit.

    The score is the method body's cognitive complexity, the measure RS012
    applies to a Python function, with a lambda's body counted toward the
    method that holds it.
    """
    code = java_code_tokens(source)
    for declaration in _callables(source):
        if declaration.body is None:
            continue
        score = java_cognitive_complexity(code, declaration.body)
        if score > COGNITIVE_COMPLEXITY_LIMIT:
            yield Violation(
                declaration.line,
                declaration.column + 1,
                RS_COGNITIVE_COMPLEXITY,
                f"{declaration.kind} '{declaration.name}' has cognitive complexity "
                f"{score}; over the limit of {COGNITIVE_COMPLEXITY_LIMIT}, "
                f"consider simplifying",
            )


def check_java_doc_value_signal(path: Path, source: str) -> Iterator[Violation]:
    """Warns when a non-trivial, non-private Java method has no Javadoc.

    A method or constructor earns the warning when its body is complex or it
    takes many parameters, the thresholds RS018 holds a Python function to.
    Whether the contract needs words is a reviewer's call; the signal points at
    the methods where a reader is likeliest to need them. A private member, an
    `@Override` method, which inherits its supertype's documentation, and
    anything in a test file never fire.
    """
    if JAVA.is_test_file(path):
        return
    code = java_code_tokens(source)
    for declaration in _callables(source):
        if declaration.doc is not None or "private" in declaration.modifiers:
            continue
        if "Override" in declaration.annotations or declaration.body is None:
            continue
        score = java_cognitive_complexity(code, declaration.body)
        params = len(declaration.parameters)
        if score < DOC_VALUE_COMPLEXITY_FLOOR and params < DOC_VALUE_PARAM_FLOOR:
            continue
        plural = "" if params == 1 else "s"
        yield Violation(
            declaration.line,
            declaration.column + 1,
            RS_DOC_VALUE_SIGNAL,
            f"{declaration.kind} '{declaration.name}' is non-trivial (cognitive "
            f"complexity {score}, {params} parameter{plural}) but has no Javadoc; "
            f"document it",
        )


def _callables(source: str) -> Iterator[JavaDeclaration]:
    """Yields each method and constructor in Java `source`."""
    for declaration in java_declarations(source):
        if declaration.kind in {"method", "constructor"}:
            yield declaration
