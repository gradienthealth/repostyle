"""Documentation-value signals warn where a docstring earns its keep.

The rules report these signals:

- RS018 warns when a non-trivial public function is under-documented.
- RS031 moves per-argument detail from body prose into an `Args:` section.
- RS032 moves return detail from body prose into a `Returns:` section.
- RS041 moves narrated exception behavior into a `Raises:` section.
- RS043 completes a present `Raises:` section from explicit raise statements.

RS041 identifies an exception through either a named body-prose reference or a
clause-leading `Raises if/when ...` condition paired with the function's sole
explicit exception type. RS043 checks explicit `raise SomeError(...)`
statements only when the function already has a `Raises:` section. RS043 skips
an exception that RS041 owns.

RS018 uses a complexity or parameter floor when a public function has no
docstring. It also flags a documented function that returns a multi-element
`tuple` without a `Returns:` section. A scalar, named type, or homogeneous
collection can stay in the summary line.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable, Iterator
from pathlib import Path

from repostyle._shared import _has_decorator, _is_test_file, _parse_python, _walk_tree
from repostyle.rules._violation import (
    RS_ARG_DESCRIBED_IN_PROSE,
    RS_DOC_VALUE_SIGNAL,
    RS_RAISE_DESCRIBED_IN_PROSE,
    RS_RAISES_SECTION_INCOMPLETE,
    RS_RETURN_DESCRIBED_IN_PROSE,
    Violation,
)
from repostyle.rules.complexity import score_block

# The presence check fires when a function scores at or above the complexity
# floor (well below RS012's limit of 15, which marks over-complexity, not mere
# worth-documenting) or has at least the parameter floor.
DOC_VALUE_COMPLEXITY_FLOOR = 5
DOC_VALUE_PARAM_FLOOR = 4

_RETURNS_SECTION_PATTERN = re.compile(r"^[ \t]*(Returns|Yields):\s*$", re.MULTILINE)
_RAISES_SECTION_PATTERN = re.compile(r"^[ \t]*Raises:\s*$", re.MULTILINE)

# These captions separate free prose from the structured entries that document
# parameters, returns, and exceptions.
_SECTION_HEADER_PATTERN = re.compile(
    r"^[ \t]*(Args|Arguments|Keyword Args|Keyword Arguments|Returns|Yields|"
    r"Raises|Attributes|Note|Notes|Example|Examples|Warning|Warnings|Todo|"
    r"See Also|References):\s*$"
)
_ARG_ENTRY_PATTERN = re.compile(r"^[ \t]+\*{0,2}(\w+)\s*(?:\([^)]*\))?\s*:")
# A `Raises:` entry names one exception, possibly module-qualified, before its
# colon.
_RAISES_ENTRY_PATTERN = re.compile(r"^[ \t]+([\w.]+)\s*:")
# The section captions whose entries name documented parameters, a subset of
# the headers above. Kept as one set so the entry collector and the header
# pattern agree on which sections hold `Args:` entries.
_ARGS_CAPTIONS = frozenset({"Args", "Arguments", "Keyword Args", "Keyword Arguments"})

# Body prose splits into clauses on sentence punctuation, but not commas, so a
# name or verb listed mid-clause is not read as its subject. The clause
# splitter steps over a backtick span before applying this; it is the fallback
# split for a body whose backticks are unbalanced.
_SENTENCE_PUNCTUATION = re.compile(r"[.;]")

# A parameter counts as "described" only when it is the subject of a body
# sentence -- it leads the clause, after an optional article, `each`, or
# "Takes" -- not merely referenced as an object inside contract prose that
# states when the function returns or no-ops.
_SUBJECT_LEAD_PATTERN = re.compile(
    r"^(?:the|an?|each|takes(?:\s+an?)?)\s+", re.IGNORECASE
)
# A backticked span is quoted code or quoted prose, not the docstring's own
# narration, so the return scan replaces each span with one placeholder before
# matching: a rule docstring quoting "Returns the lease." as an example of a
# phrasing is discussing that phrasing, not using it. The placeholder is itself
# a return object, so a narration whose object is a backticked literal still
# fires.
_CODE_SPAN_MASK = "\x00"
_CODE_SPAN_PATTERN = re.compile(r"`[^`]*`")

# The openers a real return description takes after its verb: an article, a
# quantifier, a bare literal, a pronoun, or a code span. Requiring one of a
# closed set rather than any word keeps a domain noun phrase off the rule --
# "Return visits are limited to ..." is not a return description. An unmasked
# backtick is admitted too, for the body whose unbalanced backticks left the
# clause splitter no well-formed spans to mask.
_AFTER_RETURN_VERB = (
    r"(?:(?:an?|the|each|none|nothing|self|it|this|that|true|false)\b"
    rf"|[`{_CODE_SPAN_MASK}])"
)
# The same set after a copula, minus the pronouns: "The result is that ..."
# introduces a consequence clause, not the returned thing.
_AFTER_RETURN_COPULA = (
    r"(?:(?:an?|the|each|none|nothing|true|false)\b" rf"|[`{_CODE_SPAN_MASK}])"
)

# A clause opening with a return verb restates what a `Returns:`/`Yields:`
# caption already says, so the same clause-lead test RS031 uses for a
# parameter's backtick-wrapped name applies here to the bare verb instead.
_RETURN_LEAD_PATTERN = re.compile(
    rf"^(?:returns?|yields?)\s+{_AFTER_RETURN_VERB}", re.IGNORECASE
)
# A clause naming the returned thing as its subject -- "The result is the
# parsed body.", "The value returned is `None` on a miss." -- describes the
# return without ever using the verb. The subject nouns are a closed set of
# words that can only mean this function's own output.
_RETURN_SUBJECT_PATTERN = re.compile(
    r"^(?:the\s+)?"
    r"(?:returned\s+value|return\s+value|value\s+returned|result|output)"
    rf"\s+(?:is|are)\s+{_AFTER_RETURN_COPULA}",
    re.IGNORECASE,
)
# A return verb mid-clause, where the function's input or a condition is the
# subject: "A file of any other type yields nothing." Only the third-person
# form counts, so an infinitive after a modal ("must return the borrowed
# buffer") stays off the rule.
_RETURN_MID_PATTERN = re.compile(
    rf"\b(?:returns|yields)\s+{_AFTER_RETURN_VERB}", re.IGNORECASE
)
# A pronoun directly before a mid-clause return verb refers back to something
# the prose already named -- "... when it returns a multi-element `tuple`"
# describes the callable under discussion, not the documented one. A subject
# naming an input or a condition, by contrast, is how a docstring narrates its
# own return. Adverbs between the pronoun and the verb are stepped over.
_RETURN_PRONOUN_SUBJECT_PATTERN = re.compile(
    r"\b(?:it|they|this|that|these|those|which|who|we|you|one)\s+"
    r"(?:(?:still|also|then|only|always|never|instead|already|simply)\s+)*$",
    re.IGNORECASE,
)

# RS041 anchors on the pairing of a raise verb and a backticked
# exception-shaped name in one clause, rather than a clause-lead test: the
# motivating prose ("... emits an audit event and re-raises the `FooError`")
# narrates the raise mid-clause, so neither token reliably leads. `propagate`
# is included because it is the house verb for an exception that escapes from a
# callee rather than a `raise` statement of the function's own.
_RAISE_VERB_PATTERN = re.compile(
    r"\b(?:re-?)?rais(?:e[sd]?|ing)\b|\bpropagat(?:e[sd]?|ing)\b", re.IGNORECASE
)
# A raise verb directly preceded by a negator ("never raises", "without
# raising", "rather than re-raising") states that the exception is *not* raised
# -- a legitimate body-prose claim no `Raises:` entry could carry.
_RAISE_NEGATION_PATTERN = re.compile(
    r"\b(?:never|not|cannot|without|instead\s+of|rather\s+than|no\s+longer)\s+"
    r"(?:be(?:ing)?\s+)?$",
    re.IGNORECASE,
)
# A clause-leading `Raises if/when ...` states exception behavior without
# naming its type. The narrow conditional shape avoids domain uses such as
# "raises the threshold" and gains its exception name only from the AST.
_UNNAMED_RAISE_CONDITION_PATTERN = re.compile(r"^raises\s+(?:if|when)\b", re.IGNORECASE)
# An exception reference is a whole backtick span holding one possibly-dotted
# name with the conventional `Error`/`Exception` suffix; a non-conforming
# exception name is left to review rather than guessed at.
_EXCEPTION_REFERENCE_PATTERN = re.compile(r"`([A-Za-z_][\w.]*(?:Error|Exception))`")


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
    for node in _public_functions(path, source):
        docstring = ast.get_docstring(node, clean=True)
        if docstring is None:
            continue
        body, documented, _ = _split_docstring(docstring)
        for name in _param_names(node):
            if name in documented or not _describes_param_as_subject(body, name):
                continue
            yield _violation(
                node,
                RS_ARG_DESCRIBED_IN_PROSE,
                f"parameter '{name}' is described in the docstring body of "
                f"'{node.name}'; move the description into an `Args:` entry",
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
    for node in _public_functions(path, source):
        if not _has_return_annotation(node):
            continue
        docstring = ast.get_docstring(node, clean=True)
        if docstring is None or _RETURNS_SECTION_PATTERN.search(docstring):
            continue
        body, _, _ = _split_docstring(docstring)
        if not _describes_return(body):
            continue
        yield _violation(
            node,
            RS_RETURN_DESCRIBED_IN_PROSE,
            f"the return value of '{node.name}' is described in the docstring "
            "body; move the description into a `Returns:`/`Yields:` entry",
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
    for node in _public_functions(path, source):
        docstring = ast.get_docstring(node, clean=True)
        if docstring is None:
            continue
        _, _, documented = _split_docstring(docstring)
        for name in _exceptions_described_in_prose(docstring, node):
            if name.rpartition(".")[2] in documented:
                continue
            yield _violation(
                node,
                RS_RAISE_DESCRIBED_IN_PROSE,
                f"exception '{name}' is described in the docstring prose of "
                f"'{node.name}'; move the description into a `Raises:` entry",
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
    for node in _public_functions(path, source):
        docstring = ast.get_docstring(node, clean=True)
        if docstring is None or not _RAISES_SECTION_PATTERN.search(docstring):
            continue
        _, _, documented = _split_docstring(docstring)
        narrated = {
            name.rpartition(".")[2]
            for name in _exceptions_described_in_prose(docstring, node)
        }
        for raised in _raised_exception_types(node):
            if raised in documented or raised in narrated:
                continue
            yield _violation(
                node,
                RS_RAISES_SECTION_INCOMPLETE,
                f"'{node.name}' raises '{raised}' but its `Raises:` section "
                f"does not list it; add a `Raises:` entry for it",
            )


def check_doc_value_signal(path: Path, source: str) -> Iterator[Violation]:
    """Warns when a non-trivial public function is under-documented.

    A public function with no docstring earns a warning when it is complex or
    many-argumented; a documented public function earns one when it returns a
    multi-element `tuple` but has no `Returns:` section. Trivial, non-public,
    test, and `@overload` definitions never fire.
    """
    for node in _public_functions(path, source):
        yield from _check_function(node)


def _check_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> Iterator[Violation]:
    docstring = ast.get_docstring(node, clean=False)
    params = _param_count(node)
    if docstring is None:
        score = score_block(node.body, 0)
        if score >= DOC_VALUE_COMPLEXITY_FLOOR or params >= DOC_VALUE_PARAM_FLOOR:
            plural = "" if params == 1 else "s"
            yield _violation(
                node,
                RS_DOC_VALUE_SIGNAL,
                f"function '{node.name}' is non-trivial (cognitive complexity "
                f"{score}, {params} parameter{plural}) but has no docstring; "
                "document it",
            )
        return
    if _returns_multi_element_tuple(node) and not _RETURNS_SECTION_PATTERN.search(
        docstring
    ):
        yield _violation(
            node,
            RS_DOC_VALUE_SIGNAL,
            f"function '{node.name}' returns a multi-element tuple but its "
            "docstring has no `Returns:` section; name the elements",
        )


def _describes_param_as_subject(body: str, name: str) -> bool:
    """Reports whether a body sentence documents the parameter as subject.

    A sentence describes the parameter when, after an optional leading article,
    `each`, or `Takes`, the clause opens with the backtick-wrapped name.
    """
    token = f"`{name}`"
    return _any_clause_satisfies(
        body, lambda clause: _SUBJECT_LEAD_PATTERN.sub("", clause).startswith(token)
    )


def _describes_return(body: str) -> bool:
    """Reports whether a body clause narrates the function's return value."""
    return _any_clause_satisfies(body, _clause_narrates_return)


def _exceptions_described_in_prose(
    docstring: str, node: ast.FunctionDef | ast.AsyncFunctionDef
) -> list[str]:
    """Lists exception types that unstructured docstring prose describes.

    Named references come from the body prose. An unnamed `Raises if/when ...`
    condition gains a name only when this function explicitly raises one
    distinct, statically identifiable exception type.
    """
    body, _, _ = _split_docstring(docstring)
    names = _exceptions_raised_in_prose(body)
    raised = _raised_exception_types(node)
    if (
        len(raised) == 1
        and raised[0] not in names
        and _any_clause_satisfies(
            _unstructured_prose(docstring),
            lambda clause: _UNNAMED_RAISE_CONDITION_PATTERN.match(clause) is not None,
        )
    ):
        names.append(raised[0])
    return names


def _any_clause_satisfies(body: str, holds: Callable[[str], bool]) -> bool:
    """Reports whether any clause of the body prose satisfies `holds`.

    The clause is stripped of surrounding whitespace first, so a name or verb
    is tested as a clause's leading token regardless of the prose's wrapping.
    """
    return any(holds(clause.strip()) for clause in _split_into_clauses(body))


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
    for clause in _split_into_clauses(body):
        if not _has_positive_raise_verb(clause):
            continue
        for match in _EXCEPTION_REFERENCE_PATTERN.finditer(clause):
            name = match.group(1)
            if name not in names:
                names.append(name)
    return names


def _mask_code_spans(clause: str) -> str:
    """Replaces each backticked span in the clause with one placeholder."""
    return _CODE_SPAN_PATTERN.sub(_CODE_SPAN_MASK, clause)


def _raised_exception_types(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[str]:
    """Lists the specific exception types the function's own body raises.

    Collects the class name of every `raise SomeError(...)` or `raise
    SomeError` statement reachable in the body without crossing into a nested
    function, lambda, or class, so a raise belonging to an inner scope is not
    attributed here. A bare `raise` and a `raise` of a lowercase expression
    (a caught alias, a factory call result) name no class and are skipped. A
    dotted `raise pkg.mod.FooError()` is reduced to its final segment. Each
    name is listed once, in first-encounter order.
    """
    names: list[str] = []
    # Children are pushed reversed so the LIFO stack pops them in source order,
    # keeping the listed names in first-encounter order.
    stack: list[ast.AST] = list(reversed(node.body))
    while stack:
        child = stack.pop()
        if isinstance(
            child, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda | ast.ClassDef
        ):
            continue
        if isinstance(child, ast.Raise) and child.exc is not None:
            name = _exception_type_name(child.exc)
            if name is not None and name not in names:
                names.append(name)
        stack.extend(reversed(list(ast.iter_child_nodes(child))))
    return names


def _exception_type_name(exc: ast.expr) -> str | None:
    """Returns the class name a `raise` target names, or `None`.

    A raised `Call` unwraps to its callee, so `raise FooError(...)` and `raise
    FooError` both resolve to `FooError`; a dotted `pkg.FooError` resolves to
    its final attribute. A target whose name does not start with a capital -- a
    re-raised alias like `exc`, or a lowercase factory call -- is treated as
    not naming a specific type and returns `None`.
    """
    call = exc.func if isinstance(exc, ast.Call) else exc
    if isinstance(call, ast.Name) and call.id[:1].isupper():
        return call.id
    if isinstance(call, ast.Attribute) and call.attr[:1].isupper():
        return call.attr
    return None


def _has_positive_raise_verb(clause: str) -> bool:
    """Reports whether the clause holds a raise verb in a non-negated spot.

    Each raise-verb occurrence is checked against the text directly before it,
    so `never re-raises` reads as negated while a later, unqualified `raises`
    in the same clause still counts.
    """
    return any(
        not _RAISE_NEGATION_PATTERN.search(clause[: match.start()])
        for match in _RAISE_VERB_PATTERN.finditer(clause)
    )


def _has_return_annotation(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Reports whether the return annotation is present and not `None`."""
    annotation = node.returns
    if annotation is None:
        return False
    return not (isinstance(annotation, ast.Constant) and annotation.value is None)


def _param_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Counts a function's parameters, excluding a leading `self`/`cls`."""
    return len(_param_names(node))


def _param_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Lists a function's parameter names, excluding a leading `self`/`cls`."""
    args = node.args
    positional = args.posonlyargs + args.args
    names = [arg.arg for arg in positional + args.kwonlyargs]
    if args.vararg is not None:
        names.append(args.vararg.arg)
    if args.kwarg is not None:
        names.append(args.kwarg.arg)
    if positional and positional[0].arg in ("self", "cls"):
        names = names[1:]
    return names


def _public_functions(
    path: Path, source: str
) -> Iterator[ast.FunctionDef | ast.AsyncFunctionDef]:
    """Yields each public, non-test function in a parseable source file.

    A definition is in scope when the file is not a test module and the
    function is neither underscore- nor `test_`-prefixed nor an `@overload`
    stub -- the shared subject both documentation-value rules inspect.
    """
    if _is_test_file(path):
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in _walk_tree(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if node.name.startswith(("_", "test_")):
            continue
        if _has_decorator(node, {"overload"}):
            continue
        yield node


def _returns_multi_element_tuple(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Reports whether the return annotation is a multi-element `tuple`.

    A multi-element `tuple` is an anonymous composite whose parts a single
    summary line cannot enumerate, so it warrants a `Returns:` section. The
    variadic `tuple[X, ...]` form is a homogeneous sequence, not a composite,
    and is excluded.
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


def _split_docstring(docstring: str) -> tuple[str, set[str], set[str]]:
    """Splits a cleaned docstring into body prose and documented names.

    Returns the prose body, the parameters entered under an `Args:` section,
    and the exceptions entered under a `Raises:` section, in that order. Each
    exception is reduced to its final dotted segment so a prose mention and an
    entry match whichever of the two qualifies the module. The body is the
    prose between the summary and the first Google-style section header; the
    summary itself is dropped so a name there does not read as prose.
    """
    sections = _group_by_section(docstring)
    body = "\n".join(sections.get(None, ()))
    documented_args = _entries(sections, _ARGS_CAPTIONS, _ARG_ENTRY_PATTERN)
    documented_raises = {
        name.rpartition(".")[2]
        for name in _entries(sections, {"Raises"}, _RAISES_ENTRY_PATTERN)
    }
    return body, documented_args, documented_raises


def _entries(
    sections: dict[str | None, list[str]],
    captions: frozenset[str] | set[str],
    pattern: re.Pattern[str],
) -> set[str]:
    """Returns the entry names `pattern` captures under `captions`."""
    return {
        match.group(1)
        for caption in captions
        for line in sections.get(caption, ())
        if (match := pattern.match(line))
    }


def _group_by_section(docstring: str) -> dict[str | None, list[str]]:
    """Groups a cleaned docstring's post-summary lines by their section.

    A line before the first Google-style header keys `None`; a later line keys
    the caption of the section it falls under. The summary lines are excluded,
    so the `None` group holds only the body prose after them.
    """
    lines = docstring.splitlines()
    index = 0
    while index < len(lines) and lines[index].strip():
        index += 1
    sections: dict[str | None, list[str]] = {}
    section: str | None = None
    for line in lines[index:]:
        header = _SECTION_HEADER_PATTERN.match(line)
        if header is not None:
            section = header.group(1)
        else:
            sections.setdefault(section, []).append(line)
    return sections


def _split_into_clauses(body: str) -> list[str]:
    """Splits docstring body prose into clauses on sentence punctuation.

    Newlines fold to spaces first, so a clause does not shift when the prose is
    rewrapped to a different width. A `.` or `;` ends a clause only outside a
    backtick span -- the dot of a dotted code reference like `pkg.mod.Error`
    stays within its clause rather than fragmenting it -- and a comma never
    does, so a name or verb listed mid-clause is not read as a clause of its
    own. A body with an unbalanced backtick has no well-formed spans to
    protect, so it falls back to a plain punctuation split rather than let one
    stray backtick swallow every sentence boundary after it.
    """
    flowing = body.replace("\n", " ")
    if flowing.count("`") % 2:
        return _SENTENCE_PUNCTUATION.split(flowing)
    clauses: list[str] = []
    current: list[str] = []
    in_span = False
    for char in flowing:
        if char == "`":
            in_span = not in_span
        if char in ".;" and not in_span:
            clauses.append("".join(current))
            current = []
        else:
            current.append(char)
    clauses.append("".join(current))
    return clauses


def _unstructured_prose(docstring: str) -> str:
    """Returns the summary and body prose before the first section header."""
    lines: list[str] = []
    for line in docstring.splitlines():
        if _SECTION_HEADER_PATTERN.match(line):
            break
        lines.append(line)
    return "\n".join(lines)


def _violation(
    node: ast.FunctionDef | ast.AsyncFunctionDef, rule: str, message: str
) -> Violation:
    return Violation(node.lineno, node.col_offset + 1, rule, message)
