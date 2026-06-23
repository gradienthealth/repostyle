"""Repo-style lint rules not covered by ruff or other off-the-shelf tools.

Each rule is a function taking `(path, source)` and yielding `Violation`
records. Rules are registered in the `RULES` mapping keyed by rule id.
Add a new rule by writing a function, registering it in `RULES`, and
adding a parametrized test under `tests/test_rules.py`.
"""

from __future__ import annotations

import ast
import io
import itertools
import re
import tokenize
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import NamedTuple


class Violation(NamedTuple):
    line: int
    rule: str
    message: str


RS_ACRONYM_CASING = "RS001"
RS_TEST_NAMING = "RS002"
RS_NO_MOCK_PATCH = "RS003"
RS_NO_ATTRIBUTES_BLOCK = "RS004"
RS_NO_DOUBLE_BACKTICKS = "RS005"
RS_PORT_NO_IMPLEMENTATION = "RS006"
RS_DURATION_AS_TIMEDELTA = "RS007"
RS_NO_PHI_SAFE_EXC_INFO = "RS008"
RS_DOC_FILL = "RS009"
RS_BANNED_ABBREVIATION = "RS010"
RS_DISCOURAGED_CLASS_SUFFIX = "RS011"


ACRONYMS: tuple[str, ...] = (
    "API",
    "DOB",
    "FHIR",
    "GCP",
    "HTTP",
    "ID",
    "JSON",
    "JWT",
    "MRN",
    "SMART",
    "URL",
)

PORT_IMPLEMENTATION_TOKENS: tuple[str, ...] = (
    "bigquery",
    "boto3",
    "httpx",
    "psycopg",
    "sqlalchemy",
)

TEST_NAME_PATTERN = re.compile(r"^test_[A-Z][A-Za-z0-9]*_[A-Z][A-Za-z0-9]*$")
DOUBLE_BACKTICK_PATTERN = re.compile(r"(?<!`)``(?!`)")
SECONDS_CONSTANT_PATTERN = re.compile(r"^_?[A-Z][A-Z0-9_]*_SECONDS$")
PORT_PATH_FRAGMENT = "src/fhir_ingestor/application/ports/"
FAKES_PATH_FRAGMENT = "tests/fakes/"
UNIT_TEST_PATH_FRAGMENT = "tests/unit/"

BANNED_ABBREVIATIONS: frozenset[str] = frozenset(
    {
        "btn",
        "cfg",
        "conn",
        "ctx",
        "idx",
        "mgr",
        "mngr",
        "req",
        "res",
        "resp",
        "usr",
    }
)

DISCOURAGED_CLASS_SUFFIXES: tuple[str, ...] = ("Helper", "Manager", "Util", "Utils")
TEST_CLASS_PATTERN = re.compile(r"^Test([A-Z_]|$)")


def _posix(path: Path) -> str:
    return str(path).replace("\\", "/")


def _parse_python(path: Path, source: str) -> ast.AST | None:
    if path.suffix != ".py":
        return None
    try:
        return ast.parse(source)
    except SyntaxError:
        return None


def _walk_docstring_owners(
    tree: ast.AST,
) -> Iterator[ast.AsyncFunctionDef | ast.ClassDef | ast.FunctionDef | ast.Module]:
    for node in ast.walk(tree):
        if isinstance(
            node, ast.AsyncFunctionDef | ast.ClassDef | ast.FunctionDef | ast.Module
        ):
            yield node


_CAPWORDS_WORD = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+")
_ACRONYM_SET = frozenset(ACRONYMS)


def _capwords_acronym_violations(name: str) -> Iterator[str]:
    for word in _CAPWORDS_WORD.findall(name):
        upper = word.upper()
        if upper in _ACRONYM_SET and word != upper:
            yield upper


def _identifier_words(name: str) -> Iterator[str]:
    """Yield the lowercased words composing a snake_case or CapWords name."""
    for part in name.split("_"):
        for word in _CAPWORDS_WORD.findall(part):
            yield word.lower()


_TYPE_FACTORY_NAMES = frozenset({"TypeVar", "NewType", "ParamSpec", "TypeVarTuple"})

# PEP 695 type-alias / type-parameter syntax parses only on Python 3.12+, so
# these AST node classes are absent on 3.11. Resolve them defensively to an
# empty tuple there: `isinstance(node, ())` is always False, and no PEP 695
# node can appear in a 3.11 parse anyway.
_PEP695_TYPE_ALIAS = getattr(ast, "TypeAlias", ())
_PEP695_TYPE_PARAMS = tuple(
    node
    for node in (
        getattr(ast, "TypeVar", None),
        getattr(ast, "ParamSpec", None),
        getattr(ast, "TypeVarTuple", None),
    )
    if node is not None
)


def _typevar_factory_name(call: ast.Call) -> str | None:
    """Return the unqualified name of a TypeVar-family factory call, if any."""
    func = call.func
    if isinstance(func, ast.Name):
        return func.id if func.id in _TYPE_FACTORY_NAMES else None
    if isinstance(func, ast.Attribute):
        return func.attr if func.attr in _TYPE_FACTORY_NAMES else None
    return None


def check_acronym_casing(path: Path, source: str) -> Iterator[Violation]:
    """Flag CapWords identifiers where a known acronym is not all uppercase.

    Scope: class names, PEP 695 `type` aliases, PEP 695 type parameters
    (`class C[T]`, `def f[T]`), and `TypeVar`/`NewType`/`ParamSpec`/
    `TypeVarTuple` factory calls in either `Name` or `typing.TypeVar`
    attribute form.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in ast.walk(tree):
        names: list[tuple[str, int]] = []
        if isinstance(node, ast.ClassDef):
            names.append((node.name, node.lineno))
        elif isinstance(node, _PEP695_TYPE_ALIAS):
            names.append((node.name.id, node.lineno))
        elif isinstance(node, _PEP695_TYPE_PARAMS):
            names.append((node.name, node.lineno))
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            factory = _typevar_factory_name(node.value)
            if (
                factory is not None
                and node.value.args
                and isinstance(node.value.args[0], ast.Constant)
                and isinstance(node.value.args[0].value, str)
            ):
                names.append((node.value.args[0].value, node.lineno))
        for name, lineno in names:
            if not name[:1].isupper():
                continue
            for acronym in _capwords_acronym_violations(name):
                yield Violation(
                    lineno,
                    RS_ACRONYM_CASING,
                    f"acronym '{acronym}' must stay uppercase in '{name}'",
                )


def check_test_naming(path: Path, source: str) -> Iterator[Violation]:
    """Tests under tests/unit/ must follow `test_StateUnderTest_ExpectedBehavior`."""
    if UNIT_TEST_PATH_FRAGMENT not in _posix(path):
        return
    if path.name in {"conftest.py", "__init__.py"}:
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if not node.name.startswith("test_"):
            continue
        if TEST_NAME_PATTERN.match(node.name):
            continue
        yield Violation(
            node.lineno,
            RS_TEST_NAMING,
            f"test '{node.name}' must match `test_StateUnderTest_ExpectedBehavior`",
        )


def check_no_mock_patch(path: Path, source: str) -> Iterator[Violation]:
    """`unittest.mock` and `mock` imports are rejected outside tests/fakes/."""
    if FAKES_PATH_FRAGMENT in _posix(path):
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    forbidden_modules = {"unittest.mock", "mock"}
    for node in ast.walk(tree):
        offending: str | None = None
        lineno = 0
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if alias.name in forbidden_modules or root == "mock":
                    offending = f"import {alias.name}"
                    lineno = node.lineno
                    break
        elif isinstance(node, ast.ImportFrom):
            if node.module in forbidden_modules:
                offending = f"from {node.module} import ..."
                lineno = node.lineno
            elif node.module == "unittest" and any(
                alias.name == "mock" for alias in node.names
            ):
                offending = "from unittest import mock"
                lineno = node.lineno
        if offending is None:
            continue
        yield Violation(
            lineno,
            RS_NO_MOCK_PATCH,
            f"`{offending}` rejected; use a port fake under tests/fakes/",
        )


def check_no_attributes_block(path: Path, source: str) -> Iterator[Violation]:
    """Docstrings must not use a Google `Attributes:` block."""
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in _walk_docstring_owners(tree):
        docstring = ast.get_docstring(node, clean=False)
        if docstring is None:
            continue
        if re.search(r"^\s*Attributes:\s*$", docstring, re.MULTILINE) is None:
            continue
        yield Violation(
            getattr(node, "lineno", 1),
            RS_NO_ATTRIBUTES_BLOCK,
            "use per-field attribute docstrings, not a Google `Attributes:` block",
        )


def _check_double_backticks_in_lines(source: str) -> Iterator[Violation]:
    in_fence = False
    for lineno, line in enumerate(source.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if DOUBLE_BACKTICK_PATTERN.search(line):
            yield Violation(
                lineno,
                RS_NO_DOUBLE_BACKTICKS,
                "use single backticks, not double, in prose",
            )


def check_no_double_backticks_in_md(path: Path, source: str) -> Iterator[Violation]:
    """Markdown prose may not use double backticks."""
    if path.suffix != ".md":
        return
    yield from _check_double_backticks_in_lines(source)


def check_no_double_backticks_in_docstrings(
    path: Path, source: str
) -> Iterator[Violation]:
    """Python docstring prose may not use double backticks."""
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in _walk_docstring_owners(tree):
        docstring = ast.get_docstring(node, clean=False)
        if docstring is None:
            continue
        if DOUBLE_BACKTICK_PATTERN.search(docstring):
            yield Violation(
                getattr(node, "lineno", 1),
                RS_NO_DOUBLE_BACKTICKS,
                "use single backticks, not double, in docstrings",
            )


def check_port_no_implementation(path: Path, source: str) -> Iterator[Violation]:
    """Port files must not name specific implementation libraries."""
    if PORT_PATH_FRAGMENT not in _posix(path):
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        for token in PORT_IMPLEMENTATION_TOKENS:
            if re.search(rf"\b{re.escape(token)}\b", node.value, re.IGNORECASE):
                yield Violation(
                    node.lineno,
                    RS_PORT_NO_IMPLEMENTATION,
                    f"port file names '{token}'; describe contract, not implementation",
                )


def check_duration_as_timedelta(path: Path, source: str) -> Iterator[Violation]:
    """Module-level duration constants must be `timedelta`, not raw seconds.

    Flag module-level assignments whose name matches `*_SECONDS` (with
    an optional leading underscore) and whose value is a numeric
    literal. The convention is `timedelta(seconds=N)`; raw seconds
    constants are reserved for boundaries where the wire format requires
    an integer (DB columns, JSON payloads, external library APIs), and
    those live on settings or domain fields inside class bodies, not at
    module scope.
    """
    tree = _parse_python(path, source)
    if not isinstance(tree, ast.Module):
        return
    for stmt in tree.body:
        targets: list[ast.expr]
        value: ast.expr | None
        if isinstance(stmt, ast.Assign):
            targets = list(stmt.targets)
            value = stmt.value
        elif isinstance(stmt, ast.AnnAssign):
            targets = [stmt.target]
            value = stmt.value
        else:
            continue
        if value is None:
            continue
        if not isinstance(value, ast.Constant) or not isinstance(
            value.value, int | float
        ):
            continue
        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            if SECONDS_CONSTANT_PATTERN.match(target.id) is None:
                continue
            yield Violation(
                stmt.lineno,
                RS_DURATION_AS_TIMEDELTA,
                f"'{target.id}' is a module-level duration; "
                f"use `timedelta(seconds={value.value})` instead",
            )


_LOGGING_CALL_NAMES = frozenset(
    {"debug", "info", "warning", "error", "critical", "exception", "log"}
)


def _extra_has_phi_safe(extra: ast.expr) -> bool:
    if isinstance(extra, ast.Dict):
        return any(
            isinstance(key, ast.Constant) and key.value == "phi_safe"
            for key in extra.keys
        )
    if (
        isinstance(extra, ast.Call)
        and isinstance(extra.func, ast.Name)
        and extra.func.id == "dict"
    ):
        return any(kw.arg == "phi_safe" for kw in extra.keywords)
    return False


def _has_truthy_exc_info(call: ast.Call) -> bool:
    for kw in call.keywords:
        if kw.arg != "exc_info":
            continue
        return not (
            isinstance(kw.value, ast.Constant) and kw.value.value in (False, None)
        )
    return False


def check_no_phi_safe_with_exc_info(path: Path, source: str) -> Iterator[Violation]:
    """A log record carrying `exc_info` may not be marked `phi_safe`.

    The formatter renders the record's full exception chain, and
    third-party exception messages in the chain can embed identifiers
    (request URLs, query parameters, statement parameters), so no
    `exc_info`-bearing record can be certain to be PHI-free. Detected
    when a logging-style call (`.exception(...)`, or any level method
    with a truthy `exc_info=` argument) passes a literal `extra` (a dict
    display or `dict(...)` call) containing a `"phi_safe"` key.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr not in _LOGGING_CALL_NAMES:
            continue
        extra = next((kw.value for kw in node.keywords if kw.arg == "extra"), None)
        if extra is None or not _extra_has_phi_safe(extra):
            continue
        if func.attr != "exception" and not _has_truthy_exc_info(node):
            continue
        yield Violation(
            node.lineno,
            RS_NO_PHI_SAFE_EXC_INFO,
            "record carries `exc_info`; the rendered exception chain cannot be "
            "certain PHI-free, so it must not be marked `phi_safe`",
        )


DOC_FILL_COLUMNS = 72

_SECTION_HEADERS = frozenset(
    {
        "Args:",
        "Attributes:",
        "Example:",
        "Examples:",
        "Note:",
        "Notes:",
        "Raises:",
        "Returns:",
        "Yields:",
    }
)
_LABEL_LINE_PATTERN = re.compile(r"^[A-Z][A-Za-z]*([ -][A-Z][A-Za-z]*)*:(\s|$)")
_SECTION_ENTRY_PATTERN = re.compile(r"^\S+:(\s|$)")
_BULLET_PATTERN = re.compile(r"^[-*+] ")
_COMMENT_DIRECTIVE_PATTERN = re.compile(r"^#+\s*(!|noqa\b|type:|ruff:|pragma\b)")


class _FillLine(NamedTuple):
    lineno: int
    rendered: str
    indent: int
    text: str


def _docstring_fill_lines(
    source_lines: list[str], start: int, end: int
) -> list[_FillLine]:
    lines: list[_FillLine] = []
    for lineno in range(start + 1, end + 1):
        rendered = source_lines[lineno - 1].rstrip()
        text = rendered.strip()
        if text in ('"""', "'''"):
            continue
        lines.append(_FillLine(lineno, rendered, len(rendered) - len(text), text))
    return lines


def _comment_blocks(source: str) -> Iterator[list[_FillLine]]:
    source_lines = source.splitlines()
    block: list[_FillLine] = []
    previous: tuple[int, int] | None = None
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except tokenize.TokenError:
        return
    for token in tokens:
        if token.type != tokenize.COMMENT:
            continue
        lineno, column = token.start
        if source_lines[lineno - 1][:column].strip():
            continue
        if _COMMENT_DIRECTIVE_PATTERN.match(token.string):
            if block:
                yield block
            block = []
            previous = None
            continue
        if previous != (lineno - 1, column) and block:
            yield block
            block = []
        rendered = source_lines[lineno - 1].rstrip()
        text = token.string.lstrip("#").strip()
        block.append(_FillLine(lineno, rendered, len(rendered) - len(text), text))
        previous = (lineno, column)
    if block:
        yield block


def _fill_units(lines: list[_FillLine]) -> Iterator[list[_FillLine]]:
    unit: list[_FillLine] = []
    first_indent = 0
    cont_indent: int | None = None
    in_fence = False
    section_indent: int | None = None
    entry_indent: int | None = None
    units: list[list[_FillLine]] = []

    def close() -> None:
        nonlocal unit, cont_indent
        if unit:
            units.append(unit)
        unit = []
        cont_indent = None

    for line in lines:
        if not line.text:
            close()
            continue
        if line.text.startswith("```"):
            close()
            in_fence = not in_fence
            continue
        if in_fence or line.text.startswith((">>>", "... ")):
            close()
            continue
        if line.text in _SECTION_HEADERS:
            close()
            section_indent = line.indent
            entry_indent = None
            continue
        if section_indent is not None and line.indent <= section_indent:
            section_indent = None
            entry_indent = None
        starts_entry = False
        if section_indent is not None:
            if entry_indent is None:
                entry_indent = line.indent
            starts_entry = (
                line.indent == entry_indent
                and _SECTION_ENTRY_PATTERN.match(line.text) is not None
            )
        if (
            starts_entry
            or _BULLET_PATTERN.match(line.text)
            or _LABEL_LINE_PATTERN.match(line.text)
        ):
            close()
            unit = [line]
            first_indent = line.indent
            continue
        if unit:
            if len(unit) == 1 and line.indent > first_indent:
                cont_indent = line.indent
                unit.append(line)
                continue
            expected = first_indent if cont_indent is None else cont_indent
            if line.indent == expected:
                unit.append(line)
                continue
            close()
        unit = [line]
        first_indent = line.indent
    close()
    yield from units


def _has_break_before_limit(line: _FillLine) -> bool:
    prefix_length = len(line.rendered) - len(line.text)
    break_at = line.rendered.rfind(" ", prefix_length + 1, DOC_FILL_COLUMNS + 1)
    return break_at != -1


def _fill_violations(lines: list[_FillLine]) -> Iterator[Violation]:
    for unit in _fill_units(lines):
        for line, following in itertools.pairwise(unit):
            first_word = following.text.split()[0]
            if len(line.rendered) + 1 + len(first_word) <= DOC_FILL_COLUMNS:
                yield Violation(
                    line.lineno,
                    RS_DOC_FILL,
                    f"under-wrapped line: '{first_word}' still fits within "
                    f"{DOC_FILL_COLUMNS} columns",
                )
        for line in unit:
            if len(line.rendered) <= DOC_FILL_COLUMNS or "://" in line.rendered:
                continue
            if not _has_break_before_limit(line):
                continue
            yield Violation(
                line.lineno,
                RS_DOC_FILL,
                f"line exceeds {DOC_FILL_COLUMNS} columns; rewrap the paragraph",
            )


def check_doc_fill(path: Path, source: str) -> Iterator[Violation]:
    """Docstring and comment paragraphs must fill to 72 columns.

    A paragraph line may not end while the next line's first word still
    fits within the limit, and may not run past the limit while a break
    is available. Summary lines, single-line docstrings, section
    headers, label lines, code fences, doctest lines, comment
    directives, and lines carrying URLs are exempt; bullets and section
    entries wrap as hanging paragraphs.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    source_lines = source.splitlines()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            end = node.value.end_lineno
            if end is None or end == node.value.lineno:
                continue
            yield from _fill_violations(
                _docstring_fill_lines(source_lines, node.value.lineno, end)
            )
    for block in _comment_blocks(source):
        yield from _fill_violations(block)


def check_banned_abbreviation(path: Path, source: str) -> Iterator[Violation]:
    """Flag an introduced name that drops letters from a known word.

    Scope: class, function, and parameter names, an `as` alias on an
    import, and any assignment, loop, with-as, comprehension, or walrus
    target. The name is split into its snake_case and CapWords words,
    and a word equal to a banned abbreviation (`cfg`, `ctx`, `req`,
    `resp`, `conn`, ...) is rejected in favor of the spelled-out word.
    Attribute names and string contents are not checked, so a literal
    `"cfg"` and a third-party `response.idx` access are both left alone.
    An import without an alias is left alone too, since the imported
    name is the source module's to spell, not this file's.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in ast.walk(tree):
        named: list[tuple[str, int]] = []
        if isinstance(node, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            named.append((node.name, node.lineno))
        elif isinstance(node, ast.arg):
            named.append((node.arg, node.lineno))
        elif isinstance(node, ast.alias) and node.asname is not None:
            named.append((node.asname, node.lineno))
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            named.append((node.id, node.lineno))
        for name, lineno in named:
            for word in _identifier_words(name):
                if word in BANNED_ABBREVIATIONS:
                    yield Violation(
                        lineno,
                        RS_BANNED_ABBREVIATION,
                        f"'{name}' uses the abbreviation '{word}'; spell the word out",
                    )


def check_discouraged_class_suffix(path: Path, source: str) -> Iterator[Violation]:
    """Flag a class name ending in a vague agent suffix.

    `Manager`, `Helper`, `Util`, and `Utils` name what a class loosely
    does rather than what it is, and tend to accrete unrelated
    procedures; name the responsibility instead (`ConnectionPool`, not
    `ConnectionManager`). A pytest-style test class (`Test` followed by
    a capitalized word, as in `TestContextManager`) is exempt, since it
    is named for the unit under test.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or TEST_CLASS_PATTERN.match(node.name):
            continue
        for suffix in DISCOURAGED_CLASS_SUFFIXES:
            if node.name.endswith(suffix):
                yield Violation(
                    node.lineno,
                    RS_DISCOURAGED_CLASS_SUFFIX,
                    f"class '{node.name}' ends in '{suffix}'; name the "
                    f"responsibility, not a vague agent role",
                )
                break


RULES: dict[str, Callable[[Path, str], Iterator[Violation]]] = {
    RS_ACRONYM_CASING: check_acronym_casing,
    RS_TEST_NAMING: check_test_naming,
    RS_NO_MOCK_PATCH: check_no_mock_patch,
    RS_NO_ATTRIBUTES_BLOCK: check_no_attributes_block,
    RS_NO_DOUBLE_BACKTICKS: check_no_double_backticks_in_md,
    RS_PORT_NO_IMPLEMENTATION: check_port_no_implementation,
    RS_DURATION_AS_TIMEDELTA: check_duration_as_timedelta,
    RS_NO_PHI_SAFE_EXC_INFO: check_no_phi_safe_with_exc_info,
    RS_DOC_FILL: check_doc_fill,
    RS_BANNED_ABBREVIATION: check_banned_abbreviation,
    RS_DISCOURAGED_CLASS_SUFFIX: check_discouraged_class_suffix,
}


_RS005_EXTRA_CHECKS: tuple[Callable[[Path, str], Iterator[Violation]], ...] = (
    check_no_double_backticks_in_docstrings,
)


def run_rule(rule_id: str, path: Path, source: str) -> Iterator[Violation]:
    """Run a single rule by id over one source, yielding its violations.

    RS005 covers both markdown prose and Python docstrings, registered
    under a single id; running it dispatches to both check functions.
    """
    check = RULES.get(rule_id)
    if check is None:
        return
    yield from check(path, source)
    if rule_id == RS_NO_DOUBLE_BACKTICKS:
        for extra in _RS005_EXTRA_CHECKS:
            yield from extra(path, source)


ALL_RULE_IDS: frozenset[str] = frozenset(RULES)
