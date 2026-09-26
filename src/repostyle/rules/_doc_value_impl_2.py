"""Internal doc-value implementation partition 2."""

from __future__ import annotations

import ast
import re
from collections.abc import Callable, Iterator

from repostyle.rules._doc_value_impl_3 import (
    internal_has_positive_raise_verb,
    internal_param_count,
    internal_raised_exception_types,
    internal_returns_multi_element_tuple,
    internal_split_docstring,
)
from repostyle.rules._doc_value_impl_4 import (
    internal_split_into_clauses,
    internal_unstructured_prose,
    internal_violation,
)
from repostyle.rules._violation import (
    RS_DOC_VALUE_SIGNAL,
    Violation,
)
from repostyle.rules.complexity import score_block


def internal_check_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> Iterator[Violation]:
    """Yields documentation faults for one function definition."""
    docstring = ast.get_docstring(node, clean=False)
    params = internal_param_count(node)
    if docstring is None:
        score = score_block(node.body, 0)
        if score >= DOC_VALUE_COMPLEXITY_FLOOR or params >= DOC_VALUE_PARAM_FLOOR:
            plural = "" if params == 1 else "s"
            yield internal_violation(
                node,
                RS_DOC_VALUE_SIGNAL,
                f"function '{node.name}' is non-trivial (cognitive complexity {score}, {params} parameter{plural}) but has no docstring; document it",
            )
        return
    if internal_returns_multi_element_tuple(node) and (
        not InternalRETURNS_SECTION_PATTERN.search(docstring)
    ):
        yield internal_violation(
            node,
            RS_DOC_VALUE_SIGNAL,
            f"function '{node.name}' returns a multi-element tuple but its docstring has no `Returns:` section; name the elements",
        )


DOC_VALUE_COMPLEXITY_FLOOR = 5

DOC_VALUE_PARAM_FLOOR = 4

InternalRETURNS_SECTION_PATTERN = re.compile(
    "^[ \\t]*(Returns|Yields):\\s*$", re.MULTILINE
)


def internal_describes_param_as_subject(body: str, name: str) -> bool:
    """Reports whether a body sentence documents the parameter as subject.

    A sentence describes the parameter when, after an optional leading article,
    `each`, or `Takes`, the clause opens with the backtick-wrapped name.
    """
    token = f"`{name}`"
    return _any_clause_satisfies(
        body, lambda clause: _SUBJECT_LEAD_PATTERN.sub("", clause).startswith(token)
    )


_SUBJECT_LEAD_PATTERN = re.compile(
    "^(?:the|an?|each|takes(?:\\s+an?)?)\\s+", re.IGNORECASE
)


def internal_describes_return(body: str) -> bool:
    """Reports whether a body clause narrates the function's return value."""
    return _any_clause_satisfies(body, _clause_narrates_return)


def internal_exceptions_described_in_prose(
    docstring: str, node: ast.FunctionDef | ast.AsyncFunctionDef
) -> list[str]:
    """Lists exception types that unstructured docstring prose describes.

    Named references come from the body prose. An unnamed `Raises if/when ...`
    condition gains a name only when this function explicitly raises one
    distinct, statically identifiable exception type.
    """
    body, _, _ = internal_split_docstring(docstring)
    names = _exceptions_raised_in_prose(body)
    raised = internal_raised_exception_types(node)
    if (
        len(raised) == 1
        and raised[0] not in names
        and _any_clause_satisfies(
            internal_unstructured_prose(docstring),
            lambda clause: _UNNAMED_RAISE_CONDITION_PATTERN.match(clause) is not None,
        )
    ):
        names.append(raised[0])
    return names


_UNNAMED_RAISE_CONDITION_PATTERN = re.compile(
    "^raises\\s+(?:if|when)\\b", re.IGNORECASE
)


def _any_clause_satisfies(body: str, holds: Callable[[str], bool]) -> bool:
    """Reports whether any clause of the body prose satisfies `holds`.

    The clause is stripped of surrounding whitespace first, so a name or verb
    is tested as a clause's leading token regardless of the prose's wrapping.
    """
    return any(holds(clause.strip()) for clause in internal_split_into_clauses(body))


def _clause_narrates_return(clause: str) -> bool:
    """Reports whether one body clause states what the function gives back.

    Tests the three phrasings RS032 recognizes against the clause once its
    backtick spans are masked. A mid-clause verb under a pronoun subject does
    not count, since the pronoun names a callable the prose already introduced.
    """
    masked = _mask_code_spans(clause)
    if _RETURN_LEAD_PATTERN.match(masked) or _RETURN_SUBJECT_PATTERN.match(masked):
        return True
    return any(
        not _RETURN_PRONOUN_SUBJECT_PATTERN.search(masked[: match.start()])
        for match in _RETURN_MID_PATTERN.finditer(masked)
    )


_CODE_SPAN_MASK = "\x00"
_AFTER_RETURN_COPULA = (
    f"(?:(?:an?|the|each|none|nothing|true|false)\\b|[`{_CODE_SPAN_MASK}])"
)
_AFTER_RETURN_VERB = f"(?:(?:an?|the|each|none|nothing|self|it|this|that|true|false)\\b|[`{_CODE_SPAN_MASK}])"
_RETURN_LEAD_PATTERN = re.compile(
    f"^(?:returns?|yields?)\\s+{_AFTER_RETURN_VERB}", re.IGNORECASE
)
_RETURN_SUBJECT_PATTERN = re.compile(
    f"^(?:the\\s+)?(?:returned\\s+value|return\\s+value|value\\s+returned|result|output)\\s+(?:is|are)\\s+{_AFTER_RETURN_COPULA}",
    re.IGNORECASE,
)
_RETURN_MID_PATTERN = re.compile(
    f"\\b(?:returns|yields)\\s+{_AFTER_RETURN_VERB}", re.IGNORECASE
)

_RETURN_PRONOUN_SUBJECT_PATTERN = re.compile(
    "\\b(?:it|they|this|that|these|those|which|who|we|you|one)\\s+(?:(?:still|also|then|only|always|never|instead|already|simply)\\s+)*$",
    re.IGNORECASE,
)


def _exceptions_raised_in_prose(body: str) -> list[str]:
    """Lists the exception names the body prose narrates as raised.

    A clause narrates a raise when it holds a non-negated raise verb together
    with a backticked exception-shaped name; the verb and the name pair only
    within one clause, so a raise mentioned in one sentence does not claim an
    exception named in another. A dotted name like `pkg.mod.TimeoutError` stays
    whole, since the clause split keeps a backtick span intact. Each name is
    listed once, in first-mention order.
    """
    names: list[str] = []
    for clause in internal_split_into_clauses(body):
        if not internal_has_positive_raise_verb(clause):
            continue
        for match in _EXCEPTION_REFERENCE_PATTERN.finditer(clause):
            name = match.group(1)
            if name not in names:
                names.append(name)
    return names


_EXCEPTION_REFERENCE_PATTERN = re.compile("`([A-Za-z_][\\w.]*(?:Error|Exception))`")


def _mask_code_spans(clause: str) -> str:
    """Replaces each backticked span in the clause with one placeholder."""
    return _CODE_SPAN_PATTERN.sub(_CODE_SPAN_MASK, clause)


_CODE_SPAN_PATTERN = re.compile("`[^`]*`")
