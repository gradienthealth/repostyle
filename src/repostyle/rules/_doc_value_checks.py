"""Checks that docstrings explain arguments, returns, and raises."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

from repostyle.rules._doc_value_analysis import (
    InternalRETURNS_SECTION_PATTERN,
    internal_check_function,
    internal_describes_param_as_subject,
    internal_describes_return,
    internal_exceptions_described_in_prose,
)
from repostyle.rules._docstring_entries import (
    internal_violation,
)
from repostyle.rules._function_contracts import (
    internal_has_return_annotation,
    internal_param_names,
    internal_public_functions,
    internal_raised_exception_types,
    internal_split_docstring,
)
from repostyle.rules._violation import (
    RS_ARG_DESCRIBED_IN_PROSE,
    RS_RAISE_DESCRIBED_IN_PROSE,
    RS_RAISES_SECTION_INCOMPLETE,
    RS_RETURN_DESCRIBED_IN_PROSE,
    Violation,
)


def check_arg_described_in_prose(path: Path, source: str) -> Iterator[Violation]:
    """Flags a parameter explained in the docstring body, not in `Args:`.

    A public function fires once per parameter that leads a sentence of the
    docstring's prose body as its backtick-wrapped subject while no `Args:`
    entry documents it. Per-argument detail belongs in a structured `Args:`
    section, where readers and tools look for it, not narrated in the body
    prose meant to state the unit's own contract. A parameter merely referenced
    inside the contract prose, not opening a sentence as its subject, does not
    fire, and neither does an undocumented parameter.
    """
    for node in internal_public_functions(path, source):
        docstring = ast.get_docstring(node, clean=True)
        if docstring is None:
            continue
        body, documented, _ = internal_split_docstring(docstring)
        for name in internal_param_names(node):
            if name in documented or not internal_describes_param_as_subject(
                body, name
            ):
                continue
            yield internal_violation(
                node,
                RS_ARG_DESCRIBED_IN_PROSE,
                f"parameter '{name}' is described in the docstring body of '{node.name}'; move the description into an `Args:` entry",
            )


def check_return_described_in_prose(path: Path, source: str) -> Iterator[Violation]:
    """Flags a return value described in the docstring body, not in `Returns:`.

    A public function with a non-`None` return annotation and no `Returns:` or
    `Yields:` section fires once when a clause of its docstring's prose body
    states what the call gives back. That description belongs in a structured
    `Returns:`/`Yields:` entry, where readers and tools look for it, not in the
    body prose meant to state the unit's own contract. Three phrasings count,
    each read after the clause's backtick spans are masked, so a quoted example
    is never mistaken for narration:

    1. A return verb -- `Return`, `Returns`, `Yield`, `Yields` -- opens the
       clause, followed by an article, quantifier, literal, or code span.
    2. The returned thing is the clause's subject: `The result is ...`, `The
       value returned is ...`.
    3. A return verb in its third-person form sits mid-clause, under a subject
       naming an input or a condition rather than an actor.

    Two phrasings stay exempt because prose alone cannot separate them from
    honest writing. A pronoun subject before a mid-clause verb refers to a
    callable the prose already named, so it describes that one's return rather
    than this function's. An infinitive after a modal is left alone too, since
    it carries the give-a-borrowed-thing-back sense as readily as the return
    sense. Unlike RS031, which anchors on the exact parameter name, this rule
    has no function-specific anchor, so a docstring narrating a domain action
    of returning a physical or borrowed thing can still trigger a rare false
    positive.
    """
    for node in internal_public_functions(path, source):
        if not internal_has_return_annotation(node):
            continue
        docstring = ast.get_docstring(node, clean=True)
        if docstring is None or InternalRETURNS_SECTION_PATTERN.search(docstring):
            continue
        body, _, _ = internal_split_docstring(docstring)
        if not internal_describes_return(body):
            continue
        yield internal_violation(
            node,
            RS_RETURN_DESCRIBED_IN_PROSE,
            f"the return value of '{node.name}' is described in the docstring body; move the description into a `Returns:`/`Yields:` entry",
        )


def check_raise_described_in_prose(path: Path, source: str) -> Iterator[Violation]:
    """Flags an exception narrated in docstring prose, not in `Raises:`.

    A public function fires once per exception described through either of two
    mechanical signals:

    1. A body-prose sentence pairs a backticked `*Error`/`*Exception` name with
       `raises`, `re-raises`, `propagates`, or another tense of those verbs.
    2. Unstructured prose opens a clause with `Raises if ...` or `Raises when
       ...`, and the function body names exactly one explicit exception type.

    No finding fires when a `Raises:` entry already documents the exception.
    Prose narrating a raise is a self-admission that the exception is
    contract-worthy, and raise detail belongs in the structured section where
    readers and tools look for it. The named form also reaches exceptions that
    propagate from a callee with no `raise` statement in this function. The
    unnamed form requires exactly one statically identifiable type so the rule
    never guesses which exception the prose describes. Negated raise prose and
    domain uses such as `raises the threshold` do not fire.
    """
    for node in internal_public_functions(path, source):
        docstring = ast.get_docstring(node, clean=True)
        if docstring is None:
            continue
        _, _, documented = internal_split_docstring(docstring)
        for name in internal_exceptions_described_in_prose(docstring, node):
            if name.rpartition(".")[2] in documented:
                continue
            yield internal_violation(
                node,
                RS_RAISE_DESCRIBED_IN_PROSE,
                f"exception '{name}' is described in the docstring prose of '{node.name}'; move the description into a `Raises:` entry",
            )


def check_raises_section_incomplete(path: Path, source: str) -> Iterator[Violation]:
    """Flags a `Raises:` section missing an exception the body raises outright.

    A public function with a `Raises:` section fires once for each specific
    exception type that an explicit `raise SomeError(...)` statement names but
    the section omits. A complete section lets a reader trust the stated error
    contract.

    A function without a `Raises:` section does not fire. RS041 governs that
    presence choice from the prose side. A bare `raise` and a `raise` of a
    non-class expression are ignored because neither names a specific type.
    RS043 also skips an exception that RS041 already narrates in unstructured
    docstring prose, so the rules never report the same omission twice.
    """
    for node in internal_public_functions(path, source):
        docstring = ast.get_docstring(node, clean=True)
        if docstring is None or not _RAISES_SECTION_PATTERN.search(docstring):
            continue
        _, _, documented = internal_split_docstring(docstring)
        narrated = {
            name.rpartition(".")[2]
            for name in internal_exceptions_described_in_prose(docstring, node)
        }
        for raised in internal_raised_exception_types(node):
            if raised in documented or raised in narrated:
                continue
            yield internal_violation(
                node,
                RS_RAISES_SECTION_INCOMPLETE,
                f"'{node.name}' raises '{raised}' but its `Raises:` section does not list it; add a `Raises:` entry for it",
            )


_RAISES_SECTION_PATTERN = re.compile("^[ \\t]*Raises:\\s*$", re.MULTILINE)


def check_doc_value_signal(path: Path, source: str) -> Iterator[Violation]:
    """Warns when a non-trivial public function is under-documented.

    A public function with no docstring earns a warning when it is complex or
    many-argumented; a documented public function earns one when it returns a
    multi-element `tuple` but has no `Returns:` section. Trivial, non-public,
    test, and `@overload` definitions never fire.
    """
    for node in internal_public_functions(path, source):
        yield from internal_check_function(node)
