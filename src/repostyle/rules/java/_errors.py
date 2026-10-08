"""Java error-handling rules: an ignored exception says why it is safe."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from repostyle.languages import JAVA, JavaToken, comment_text, lex_java
from repostyle.rules._violation import RS_EMPTY_CATCH_REASON, Violation


def check_empty_catch_reason(path: Path, source: str) -> Iterator[Violation]:
    """An empty Java `catch` block explains in place why it ignores the error.

    Google Java style allows a `catch` block to do nothing only when a comment
    in it says why that is justified. A block holding no comment, or only a
    pointer to an explanation elsewhere (`// See method javadoc.`) or a bare
    label (`// ignored`), leaves the reader to rediscover the reason. In a
    test, an exception whose variable is named `expected`, or begins with it,
    may be ignored without a comment, as Google Java style allows.
    """
    tokens = lex_java(source)
    is_test = JAVA.is_test_file(path)
    for index, token in enumerate(tokens):
        if token.text != "catch" or token.kind != "ident":
            continue
        block = _empty_block_after(tokens, index + 1)
        if block is None:
            continue
        variable, comments = block
        if is_test and variable.startswith("expected"):
            continue
        reason = " ".join(_comment_prose(comment) for comment in comments)
        if _is_reason(reason):
            continue
        yield Violation(
            token.line,
            token.column + 1,
            RS_EMPTY_CATCH_REASON,
            "an empty `catch` block must say why ignoring the exception is safe; "
            "write the reason in a comment inside the block",
        )


def _empty_block_after(
    tokens: tuple[JavaToken, ...], index: int
) -> tuple[str, list[JavaToken]] | None:
    """Reads the `(...) {...}` after a `catch`, if its block holds no code.

    Returns:
        The caught exception's variable name and the comments inside the block,
        or `None` when the block holds a statement.
    """
    variable, index = _catch_parameter(tokens, index)
    if index >= len(tokens) or tokens[index].text != "{":
        return None
    comments: list[JavaToken] = []
    for token in tokens[index + 1 :]:
        if token.text == "}":
            return variable, comments
        if token.kind not in _COMMENT_KINDS:
            return None
        comments.append(token)
    return None


def _catch_parameter(tokens: tuple[JavaToken, ...], index: int) -> tuple[str, int]:
    """Reads a `catch` clause's parenthesized parameter starting at `index`.

    Returns:
        The parameter's variable name, the last identifier inside the
        parentheses, and the index just past the closing `)`.
    """
    variable = ""
    depth = 0
    while index < len(tokens):
        token = tokens[index]
        index += 1
        depth += {"(": 1, ")": -1}.get(token.text, 0)
        if token.kind == "ident":
            variable = token.text
        if depth == 0 and token.text == ")":
            break
    return variable, index


_COMMENT_KINDS = frozenset({"line_comment", "block_comment", "doc_comment"})


def _comment_prose(comment: JavaToken) -> str:
    """Returns a comment's words, with its markers and gutter stripped."""
    if comment.kind == "line_comment":
        return comment_text(comment.text)
    body = comment.text.removeprefix("/**").removeprefix("/*").removesuffix("*/")
    return " ".join(line.strip().lstrip("*").strip() for line in body.splitlines())


def _is_reason(text: str) -> bool:
    """Reports whether a comment gives a reason, not a pointer or a label."""
    words = re.sub(r"[^\w\s-]", "", text).strip().lower()
    if not words or words in _BARE_LABELS:
        return False
    return not words.startswith("see ")


_BARE_LABELS = frozenset(
    {
        "do nothing",
        "empty",
        "expected",
        "ignore",
        "ignored",
        "intentionally empty",
        "no-op",
        "noop",
        "nothing",
        "nothing to do",
        "swallow",
        "swallowed",
    }
)
