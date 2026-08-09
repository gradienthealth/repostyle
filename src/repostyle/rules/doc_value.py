"""Documentation-value signals: warn where a docstring earns its keep.

Five rules live here, all advising that documentation land where it is most
useful rather than demanding it everywhere. RS018 scores a function's
documentation value and warns when a non-trivial public function is
under-documented; RS031 warns when per-argument detail is narrated in the
docstring body instead of a structured `Args:` section; RS032 warns when the
return value is narrated there instead of a `Returns:` section; RS041 warns
when a raised exception is narrated there instead of a `Raises:` section; RS043
warns when a function has a `Raises:` section but an exception its body raises
outright is missing from it.

RS041 and RS043 are complementary halves of the same concern, split by their
signal. RS041 is prose-driven -- it fires on an exception narrated in the body
with a raise verb, the only signal available when the exception propagates from
a callee. RS043 is AST-driven -- it fires on an explicit `raise SomeError(...)`
statement absent from an existing `Raises:` section. Where both could reach one
exception, RS043 yields, skipping any exception RS041 already narrates.

RS018 has two triggers. The presence trigger fires when a complex or
many-argumented public function carries no docstring. The `Returns:` trigger
fires when a documented function returns a multi-element `tuple` -- an
anonymous composite whose parts a single summary line cannot name; a scalar, a
named type, or a homogeneous collection is left to the summary line.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable, Iterator
from pathlib import Path

from repostyle._shared import _has_decorator, _is_test_file, _parse_python
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

# A Google-style section header is a known caption alone on its line. Anything
# before the first header is the body prose RS031 and RS041 scan; the `Args:`
# and `Raises:` blocks' entries are the names already documented there.
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
# A clause opening with `Return`/`Returns` restates the verb a `Returns:`
# section already implies, so the same clause-lead test RS031 uses for a
# parameter's backtick-wrapped name applies here to the bare verb instead. The
# verb must be followed by one of a closed set of common openers for an actual
# return description (an article, a literal, a pronoun, or a backtick), not
# just any word -- otherwise "Return visits are limited to ..." (a domain noun
# phrase, not the verb) would false-positive on a bare `^returns?\b` match.
_RETURN_LEAD_PATTERN = re.compile(
    r"^returns?\s+"
    r"(?:(?:a|an|the|each|none|nothing|self|it|this|that|true|false)\b|`)",
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
    `Yields:` section fires once when a sentence in the docstring's prose body
    opens with `Return` or `Returns` as its leading clause. That verb is what a
    `Returns:` section caption already states, so the description belongs in a
    structured `Returns:`/`Yields:` entry, where readers and tools look for it,
    not narrated in the body prose meant to state the unit's own contract.
    Unlike RS031, which anchors on the exact parameter name, this has no
    function-specific anchor to check the clause against, so a docstring
    genuinely narrating a `return`-the-item domain action (returning a physical
    or borrowed thing, not this function's return value) can rarely trigger a
    false positive; the closed opener set narrows but does not eliminate that
    risk.
    """
    for node in _public_functions(path, source):
        if not _has_return_annotation(node):
            continue
        docstring = ast.get_docstring(node, clean=True)
        if docstring is None or _RETURNS_SECTION_PATTERN.search(docstring):
            continue
        body, _, _ = _split_docstring(docstring)
        if not _describes_return_up_front(body):
            continue
        yield _violation(
            node,
            RS_RETURN_DESCRIBED_IN_PROSE,
            f"the return value of '{node.name}' is described in the docstring "
            "body; move the description into a `Returns:`/`Yields:` entry",
        )


def check_raise_described_in_prose(path: Path, source: str) -> Iterator[Violation]:
    """Flags an exception narrated in the docstring body, not in `Raises:`.

    A public function fires once per backticked `*Error`/`*Exception` name
    sharing a body-prose sentence with a raise verb (`raises`, `re-raises`,
    `propagates`, and their tenses) while no `Raises:` entry documents that
    exception. Prose narrating a raise is a self-admission that the exception
    is contract-worthy, and raise detail belongs in a structured `Raises:`
    section, where readers and tools look for it, not in the body prose meant
    to state the unit's own contract. The prose is also the one mechanical
    signal available when the exception propagates from a callee with no
    `raise` statement in the function itself, the case an AST-based checker
    cannot see. A sentence whose raise verb is negated (`never raises ...`)
    does not fire, and neither does an exception the docstring leaves
    unmentioned.
    """
    for node in _public_functions(path, source):
        docstring = ast.get_docstring(node, clean=True)
        if docstring is None:
            continue
        body, _, documented = _split_docstring(docstring)
        for name in _exceptions_raised_in_prose(body):
            if name.rpartition(".")[2] in documented:
                continue
            yield _violation(
                node,
                RS_RAISE_DESCRIBED_IN_PROSE,
                f"exception '{name}' is described in the docstring body of "
                f"'{node.name}'; move the description into a `Raises:` entry",
            )


def check_raises_section_incomplete(path: Path, source: str) -> Iterator[Violation]:
    """Flags a `Raises:` section missing an exception the body raises outright.

    A public function that already carries a `Raises:` section fires once per
    specific exception type its own body raises with an explicit `raise
    SomeError(...)` statement while no `Raises:` entry names it. Once a
    function documents its exceptions at all, the section should be complete,
    so a reader trusts it; a raise the section omits silently understates the
    contract. A function with no `Raises:` section does not fire -- whether to
    document exceptions at all is a presence choice RS041 governs from the
    prose side. A bare `raise` re-raising the caught exception and a `raise` of
    a non-class expression are ignored, since neither names a specific type,
    and an exception RS041 already narrates in the body prose is left to RS041
    so the two rules never flag one exception twice.
    """
    for node in _public_functions(path, source):
        docstring = ast.get_docstring(node, clean=True)
        if docstring is None or not _RAISES_SECTION_PATTERN.search(docstring):
            continue
        body, _, documented = _split_docstring(docstring)
        narrated = {
            name.rpartition(".")[2] for name in _exceptions_raised_in_prose(body)
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
    return _any_clause_leads_with(
        body, lambda clause: _SUBJECT_LEAD_PATTERN.sub("", clause).startswith(token)
    )


def _describes_return_up_front(body: str) -> bool:
    """Reports whether a body sentence narrates the return value up front.

    A sentence narrates the return value when its clause opens with `Return` or
    `Returns` followed by a description, rather than the word appearing as an
    unrelated domain noun (`Return visits are limited to ...`).
    """
    return _any_clause_leads_with(
        body, lambda clause: _RETURN_LEAD_PATTERN.match(clause) is not None
    )


def _any_clause_leads_with(body: str, leads_with: Callable[[str], bool]) -> bool:
    """Reports whether any clause of the body prose satisfies `leads_with`.

    The clause is stripped of surrounding whitespace first, so a name or verb
    is tested as a clause's leading token regardless of the prose's wrapping.
    """
    return any(leads_with(clause.strip()) for clause in _split_into_clauses(body))


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
    for node in ast.walk(tree):
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


def _violation(
    node: ast.FunctionDef | ast.AsyncFunctionDef, rule: str, message: str
) -> Violation:
    return Violation(node.lineno, node.col_offset + 1, rule, message)
