"""Documentation-value signals: warn where a docstring earns its keep.

Two rules live here, both advising that documentation land where it is
most useful rather than demanding it everywhere. RS018 scores a
function's documentation value and warns when a non-trivial public
function is under-documented; RS031 warns when per-argument detail is
narrated in the docstring body instead of a structured `Args:` section.

RS018 has three triggers. The presence trigger fires when a complex or
many-argumented public function carries no docstring. The `Args:`
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

from pystyle.rules._shared import _has_decorator, _is_test_file, _parse_python
from pystyle.rules._violation import (
    RS_ARG_DESCRIBED_IN_PROSE,
    RS_DOC_VALUE_SIGNAL,
    Violation,
)
from pystyle.rules.complexity import _score_block

# The presence check fires when a function scores at or above the
# complexity floor (well below RS012's limit of 15, which marks
# over-complexity, not mere worth-documenting) or has at least the
# parameter floor. The `Args:` trigger keeps its own parameter floor.
DOC_VALUE_COMPLEXITY_FLOOR = 5
DOC_VALUE_PARAM_FLOOR = 4
DOC_VALUE_ARGS_PARAM_FLOOR = 4

_ARGS_SECTION_PATTERN = re.compile(r"^[ \t]*(Args|Arguments):\s*$", re.MULTILINE)
_RETURNS_SECTION_PATTERN = re.compile(r"^[ \t]*(Returns|Yields):\s*$", re.MULTILINE)

# A Google-style section header is a known caption alone on its line.
# Anything before the first header is the body prose RS031 scans; the
# `Args:` block's entries are the parameters already documented there.
_SECTION_HEADER_PATTERN = re.compile(
    r"^[ \t]*(Args|Arguments|Keyword Args|Keyword Arguments|Returns|Yields|"
    r"Raises|Attributes|Note|Notes|Example|Examples|Warning|Warnings|Todo|"
    r"See Also|References):\s*$"
)
_ARG_ENTRY_PATTERN = re.compile(r"^[ \t]+\*{0,2}(\w+)\s*(?:\([^)]*\))?\s*:")

# A parameter counts as "described" only when it is the subject of a
# body sentence — it leads the clause, after an optional article or
# "Takes" — not merely referenced as an object inside contract prose
# that states when the function returns or no-ops.
_SUBJECT_LEAD_PATTERN = re.compile(
    r"^(?:the|an?|each|takes(?:\s+an?)?)\s+", re.IGNORECASE
)


def check_arg_described_in_prose(path: Path, source: str) -> Iterator[Violation]:
    """Flag a parameter explained in the docstring body, not in `Args:`.

    A public function fires once per parameter that leads a sentence of
    the docstring's prose body as its backtick-wrapped subject while no
    `Args:` entry documents it. Per-argument detail belongs in a
    structured `Args:` section, where readers and tools look for it, not
    narrated in the body prose meant to state the unit's own contract. A
    parameter merely referenced inside that contract prose, rather than
    described as a sentence's subject, does not fire; nor does an
    undocumented one, so the rule relocates explanation a writer already
    gave rather than demanding new prose.
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
        docstring = ast.get_docstring(node, clean=True)
        if docstring is None:
            continue
        body, documented = _body_and_documented_args(docstring)
        for name in _param_names(node):
            if name in documented or not _describes_param_as_subject(body, name):
                continue
            yield _violation(
                node,
                RS_ARG_DESCRIBED_IN_PROSE,
                f"parameter '{name}' is described in the docstring body of "
                f"'{node.name}'; move the description into an `Args:` entry",
            )


def check_doc_value_signal(path: Path, source: str) -> Iterator[Violation]:
    """Warn when a non-trivial public function is under-documented.

    A public function with no docstring earns a warning when it is
    complex or many-argumented; a documented public function earns one
    when it has many parameters but no `Args:` section, or returns a
    multi-element `tuple` but no `Returns:` section. Trivial,
    non-public, test, and `@overload` definitions never fire.
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


def _body_and_documented_args(docstring: str) -> tuple[str, set[str]]:
    """Split a cleaned docstring into its body prose and documented args.

    The body is the prose between the summary and the first Google-style
    section header; the documented args are the names entered under an
    `Args:` section. Trim the summary so a parameter named there does
    not read as prose, and stop the body at the first section header.
    """
    lines = docstring.splitlines()
    index = 0
    while index < len(lines) and lines[index].strip():
        index += 1
    body: list[str] = []
    documented: set[str] = set()
    section: str | None = None
    for line in lines[index:]:
        header = _SECTION_HEADER_PATTERN.match(line)
        if header is not None:
            section = header.group(1)
        elif section is None:
            body.append(line)
        elif section in ("Args", "Arguments", "Keyword Args", "Keyword Arguments"):
            entry = _ARG_ENTRY_PATTERN.match(line)
            if entry is not None:
                documented.add(entry.group(1))
    return "\n".join(body), documented


def _describes_param_as_subject(body: str, name: str) -> bool:
    """Report whether a body sentence documents the parameter as subject.

    A sentence describes the parameter when, after an optional leading
    article or `Takes`, the clause opens with the backtick-wrapped name.
    Sentences split on `.`, `;`, and newlines but not commas, so a name
    listed mid-clause in contract prose is not read as a description.
    """
    token = f"`{name}`"
    for clause in re.split(r"[.;\n]", body):
        if _SUBJECT_LEAD_PATTERN.sub("", clause.strip()).startswith(token):
            return True
    return False


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
                RS_DOC_VALUE_SIGNAL,
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
            RS_DOC_VALUE_SIGNAL,
            f"function '{node.name}' has {params} parameters but its docstring "
            "has no `Args:` section; document them in one rather than in prose",
        )
    if _returns_multi_element_tuple(node) and not _RETURNS_SECTION_PATTERN.search(
        docstring
    ):
        yield _violation(
            node,
            RS_DOC_VALUE_SIGNAL,
            f"function '{node.name}' returns a multi-element tuple but its "
            "docstring has no `Returns:` section; name the elements",
        )


def _param_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Count a function's parameters, excluding a leading `self`/`cls`."""
    return len(_param_names(node))


def _param_names(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """List a function's parameter names, excluding a leading `self`/`cls`."""
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


def _returns_multi_element_tuple(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Report whether the return annotation is a multi-element `tuple`.

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


def _violation(
    node: ast.FunctionDef | ast.AsyncFunctionDef, rule: str, message: str
) -> Violation:
    return Violation(node.lineno, node.col_offset + 1, rule, message)
