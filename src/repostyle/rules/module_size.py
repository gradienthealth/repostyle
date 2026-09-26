"""Source and test module size warnings."""

from __future__ import annotations

import ast
import io
import tokenize
from collections.abc import Iterator
from pathlib import Path

from repostyle._shared import (
    _is_test_file,
    _parse_python,
    _repostyle_table,
    find_pyproject,
)
from repostyle.rules._violation import (
    RS_SOURCE_MODULE_SIZE,
    RS_TEST_MODULE_SIZE,
    Violation,
)

MAX_SOURCE_FILE_LINES_KEY = "max-source-file-lines"
MAX_TEST_FILE_LINES_KEY = "max-test-file-lines"
DEFAULT_MAX_SOURCE_FILE_LINES = 250
DEFAULT_MAX_TEST_FILE_LINES = 500


def check_source_module_size(path: Path, source: str) -> Iterator[Violation]:
    """Warns when a source module exceeds its configured code-line limit.

    A large production module can hide distinct responsibilities behind one
    import boundary. The default limit is 250 physical code lines. Blank
    lines, comment-only lines, and module, class, and function docstrings do
    not count. Test modules use their independent RS062 limit instead.
    """
    if path.suffix != ".py" or _is_test_file(path):
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    limit = _max_file_lines(
        path, MAX_SOURCE_FILE_LINES_KEY, DEFAULT_MAX_SOURCE_FILE_LINES
    )
    code_lines = _module_code_lines(tree, source)
    if len(code_lines) <= limit:
        return
    yield Violation(
        min(code_lines),
        1,
        RS_SOURCE_MODULE_SIZE,
        f"source module has {len(code_lines)} code lines (limit: {limit}); split "
        f"distinct responsibilities into cohesive modules",
    )


def check_test_module_size(path: Path, source: str) -> Iterator[Violation]:
    """Warns when a test module exceeds its configured code-line limit.

    Large test modules can reveal coupled production responsibilities or tests
    that cover unrelated behavior together. The default limit is 500 physical
    code lines. Blank lines, comment-only lines, and module, class, and
    function docstrings do not count.
    """
    if not _is_test_file(path):
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    limit = _max_file_lines(path, MAX_TEST_FILE_LINES_KEY, DEFAULT_MAX_TEST_FILE_LINES)
    code_lines = _module_code_lines(tree, source)
    if len(code_lines) <= limit:
        return
    yield Violation(
        min(code_lines),
        1,
        RS_TEST_MODULE_SIZE,
        f"test module has {len(code_lines)} code lines (limit: {limit}); review "
        f"responsibility boundaries and split tests into cohesive modules",
    )


def _max_file_lines(path: Path, key: str, default: int) -> int:
    """Returns the positive module line limit configured under `key`."""
    table = _repostyle_table(find_pyproject(path))
    configured = table.get(key, default)
    if (
        not isinstance(configured, int)
        or isinstance(configured, bool)
        or configured <= 0
    ):
        raise ValueError(f"`{key}` must be a positive integer")
    return configured


def _module_code_lines(tree: ast.AST, source: str) -> set[int]:
    """Returns the physical lines containing non-docstring Python tokens."""
    source_lines = source.split("\n")
    docstrings = tuple(_docstring_spans(tree, source_lines))
    ignored = {
        tokenize.COMMENT,
        tokenize.DEDENT,
        tokenize.ENCODING,
        tokenize.ENDMARKER,
        tokenize.INDENT,
        tokenize.NEWLINE,
        tokenize.NL,
    }
    code_lines: set[int] = set()
    tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    for token in tokens:
        if token.type in ignored:
            continue
        if token.type == tokenize.ERRORTOKEN and token.string.isspace():
            continue
        if any(_span_contains(span, token.start, token.end) for span in docstrings):
            continue
        code_lines.update(
            lineno
            for lineno in range(token.start[0], token.end[0] + 1)
            if source_lines[lineno - 1].strip()
        )
    return code_lines


def _docstring_spans(
    tree: ast.AST, source_lines: list[str]
) -> Iterator[tuple[tuple[int, int], tuple[int, int]]]:
    """Yields the source span of each module, class, or function docstring."""
    owners = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for owner in ast.walk(tree):
        if not isinstance(owner, owners) or not owner.body:
            continue
        statement = owner.body[0]
        if not (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        ):
            continue
        end_lineno = statement.end_lineno or statement.lineno
        end_col_offset = statement.end_col_offset or statement.col_offset
        yield (
            (
                statement.lineno,
                _character_column(
                    source_lines[statement.lineno - 1], statement.col_offset
                ),
            ),
            (
                end_lineno,
                _character_column(source_lines[end_lineno - 1], end_col_offset),
            ),
        )


def _character_column(line: str, byte_column: int) -> int:
    """Converts an AST UTF-8 byte offset to a tokenizer character offset."""
    return len(line.encode("utf-8")[:byte_column].decode("utf-8"))


def _span_contains(
    span: tuple[tuple[int, int], tuple[int, int]],
    start: tuple[int, int],
    end: tuple[int, int],
) -> bool:
    """Reports whether a token falls wholly inside a source span."""
    return span[0] <= start and end <= span[1]
