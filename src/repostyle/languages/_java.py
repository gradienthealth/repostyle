"""Java lexing, comment extraction, block spans, and test-file layout.

The lexer is a single regular-expression pass, not a parser. It separates
comments, Javadoc, and literals from code, and leaves each code token as an
identifier, a number, or one punctuation character, which is all the structural
scans above it need: a rule reasons over braces and declarations, never over
expressions.
"""

from __future__ import annotations

import bisect
import re
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

from repostyle.languages._model import CommentToken


class JavaToken(NamedTuple):
    kind: str
    """One of the `_KINDS` group names, such as `ident` or `doc_comment`."""
    text: str
    """The token's source text, delimiters included."""
    line: int
    """1-based line the token starts on."""
    column: int
    """0-based column the token starts at."""
    end_line: int
    """1-based line holding the token's last character."""


def java_block_spans(source: str) -> Iterator[tuple[int, int]]:
    """Yields the inclusive line span of each statement in Java `source`.

    The spans are what a `style: ignore-block` directive can cover, matched to
    the statements Python's spans are:

    - A declaration runs from its Javadoc or first annotation through the `;`
      that ends it or the `}` that closes its body.
    - An `if` runs through its `else` branches, and a `try` through its `catch`
      and `finally` blocks.
    - A statement nested in a body yields its own span.

    A line or block comment opens no statement, so a directive written above
    one attaches to the statement below it.
    """
    tokens = [t for t in lex_java(source) if t.kind not in _PLAIN_COMMENT_KINDS]
    starts: list[int | None] = [None]
    for index, token in enumerate(tokens):
        starts[-1] = starts[-1] or token.line
        if token.kind == "doc_comment":
            continue
        if token.text == "{":
            starts.append(None)
            continue
        if token.text not in _STATEMENT_ENDS:
            continue
        if token.text == "}" and len(starts) > 1:
            starts.pop()
            if _is_continued(tokens, index):
                continue
        yield (starts[-1] or token.line, token.line)
        starts[-1] = None


_STATEMENT_ENDS = frozenset({";", "}"})


def _is_continued(tokens: list[JavaToken], index: int) -> bool:
    """Reports whether an `else`, `catch`, or `finally` follows a `}`."""
    following = index + 1
    return following < len(tokens) and tokens[following].text in _CONTINUATIONS


# A keyword that continues the statement a `}` would otherwise end, so a
# directive above an `if` or `try` covers its `else`, `catch`, and `finally`.
_CONTINUATIONS = frozenset({"else", "catch", "finally"})


def java_comments(source: str) -> Iterator[CommentToken]:
    """Yields each `//` line comment in Java `source`.

    A `//` inside a string, a text block, a character literal, or a block
    comment is not a comment, since the lexer consumes each of those whole.
    Block comments and Javadoc are not line comments and are not yielded.
    """
    lines = source.splitlines()
    for token in lex_java(source):
        if token.kind != "line_comment":
            continue
        prefix = lines[token.line - 1][: token.column]
        yield CommentToken(token.line, token.column, token.text, bool(prefix.strip()))


def is_java_test_file(path: Path) -> bool:
    """Reports whether a path holds Java tests by location or class name.

    A file under a Maven or Gradle `src/test/` tree is a test source, as is a
    class named for the `Test`, `Tests`, or `IT` suffix convention outside it.
    """
    posix = str(path).replace("\\", "/")
    return "src/test/" in posix or _TEST_NAME_PATTERN.search(posix) is not None


_TEST_NAME_PATTERN = re.compile(r"(Test|Tests|IT)\.java$")


_PLAIN_COMMENT_KINDS = frozenset({"line_comment", "block_comment"})


@lru_cache(maxsize=128)
def lex_java(source: str) -> tuple[JavaToken, ...]:
    """Splits Java `source` into comment, literal, and code tokens.

    An unterminated block comment, text block, or string runs to the end of its
    line or the source rather than raising, so a file mid-edit still yields the
    tokens before the fault. A character no group claims becomes a
    one-character `op` token.

    Returns:
        Every non-whitespace token in source order.
    """
    line_starts = [0, *(match.end() for match in re.finditer("\n", source))]
    tokens: list[JavaToken] = []
    for match in _TOKEN_PATTERN.finditer(source):
        kind = match.lastgroup
        if kind is None or kind == "space":
            continue
        start, end = match.span()
        line = bisect.bisect_right(line_starts, start)
        end_line = bisect.bisect_right(line_starts, max(start, end - 1))
        column = start - line_starts[line - 1]
        tokens.append(JavaToken(kind, match.group(), line, column, end_line))
    return tuple(tokens)


# Order matters: Javadoc before a block comment, a text block before a string,
# and every literal before the catch-all `op`.
_KINDS = (
    ("space", r"\s+"),
    ("doc_comment", r"/\*\*(?!/)(?:.*?\*/|.*)"),
    ("block_comment", r"/\*(?:.*?\*/|.*)"),
    ("line_comment", r"//[^\n]*"),
    ("text_block", r'"""(?:\\.|.)*?(?:"""|\Z)'),
    ("string", r'"(?:\\.|[^"\\\n])*"?'),
    ("char", r"'(?:\\.|[^'\\\n])*'?"),
    ("number", r"\.?\d(?:[eEpP][+-]|[\w.])*"),
    ("ident", r"non-sealed\b|[^\W\d]\w*|\$[\w$]*"),
    ("op", r"."),
)

_TOKEN_PATTERN = re.compile(
    "|".join(f"(?P<{name}>{pattern})" for name, pattern in _KINDS), re.DOTALL
)
