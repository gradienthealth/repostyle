"""Python parsing, comment extraction, block spans, and test-file layout."""

from __future__ import annotations

import ast
import io
import re
import tokenize
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from repostyle.languages._model import CommentToken


def python_comments(source: str) -> Iterator[CommentToken]:
    """Yields each comment token in Python `source` via the tokenizer.

    Tokens are yielded as the tokenizer produces them, so a fault in the tail
    still surfaces the comments before it.
    """
    source_lines = source.splitlines()
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type != tokenize.COMMENT:
                continue
            lineno, column = token.start
            is_trailing = bool(source_lines[lineno - 1][:column].strip())
            yield CommentToken(lineno, column, token.string, is_trailing)
    except (tokenize.TokenError, SyntaxError):
        # An unterminated tail raises TokenError; inconsistent indentation
        # raises IndentationError/TabError (SyntaxError subclasses). Stop at
        # the fault and keep the comments already surfaced.
        return


def python_block_spans(source: str) -> Iterator[tuple[int, int]]:
    """Yields the inclusive line span of each statement in Python `source`.

    A decorated statement opens at its first decorator, so a directive written
    above the decorators still covers the definition they wrap. A source that
    does not parse has no spans.
    """
    tree = parse_python(source)
    if tree is None:
        return
    for node in ast.walk(tree):
        if not isinstance(node, ast.stmt):
            continue
        decorators = getattr(node, "decorator_list", [])
        start = min([node.lineno, *(d.lineno for d in decorators)])
        yield (start, node.end_lineno or node.lineno)


@lru_cache(maxsize=128)
def parse_python(source: str) -> ast.Module | None:
    """Returns the parsed module of `source`, or `None` when it does not parse.

    The cache is shared by every rule and the suppression parser, so a file is
    parsed once however many readers it has.
    """
    try:
        return ast.parse(source)
    except SyntaxError:
        return None


def is_python_test_file(path: Path) -> bool:
    """Reports whether a path is a Python test module by location or name."""
    posix = str(path).replace("\\", "/")
    return "tests/" in posix or TEST_FILE_PATTERN.search(posix) is not None


TEST_FILE_PATTERN = re.compile(r"(^|/)(test_[^/]*|[^/]*_test)\.py$")
