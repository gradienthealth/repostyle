"""Checks and reflows prose split across implicitly concatenated strings."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

from repostyle._shared import _join_source_lines, _parse_python
from repostyle.rules._display_width import internal_display_width
from repostyle.rules._reflow import DOC_FILL_COLUMNS
from repostyle.rules._violation import RS_STRING_FILL, Violation


def check_string_fill(path: Path, source: str) -> Iterator[Violation]:
    """Prose split across adjacent string literals must fill to 79 columns.

    Python joins adjacent string literals into one value, so a long message is
    written as a parenthesized run of pieces, one per line. Once a piece is
    edited, the run no longer fills: a line ends early while the next word
    still fits, or runs past the limit while a break is available. The rule
    applies RS009's greedy fill to such a run, at the same 79 columns.

    A run counts as prose when every line holds exactly one plain or f-string
    piece at a shared indent and in a shared quote style, each break falls
    after a single space, the value ends on `.`, `!`, or `?`, and no piece
    holds an HTML tag, a double space, or a newline escape. A run broken at
    syntax rather than at words, such as SQL clauses or a filter expression,
    fails one of those tests and is left alone. Raw, bytes, and triple-quoted
    strings never count, and neither does a docstring, which RS009 owns. An
    f-string placeholder is one unbreakable word.
    """
    if path.suffix != ".py":
        return
    tree = _parse_python(path, source)
    if tree is None:
        return
    for run in _prose_runs(tree, source.splitlines()):
        layout = _greedy_layout(run)
        if layout != run.layout:
            yield _first_fault(run, layout)


def fix_string_fill(
    path: Path, source: str, skip_lines: frozenset[int] = frozenset()
) -> str:
    """Rewraps each prose string run `check_string_fill` reports.

    The rewrite breaks only at the spaces the run already holds and keeps each
    space at the end of its piece, so the string's value is unchanged. A piece
    takes the `f` prefix only when it holds a placeholder, with its literal
    braces doubled to match. A run with a line in `skip_lines` is left alone.

    Returns:
        The source with prose string runs rewrapped, unchanged when nothing
        reflows.
    """
    if path.suffix != ".py":
        return source
    tree = _parse_python(path, source)
    if tree is None:
        return source
    source_lines = source.splitlines()
    replacements: list[_Replacement] = []
    for run in _prose_runs(tree, source_lines):
        if any(piece.lineno in skip_lines for piece in run.pieces):
            continue
        layout = _greedy_layout(run)
        if layout == run.layout:
            continue
        rendered: list[str] = []
        words = run.words
        for count in layout:
            line_words, words = words[:count], words[count:]
            rendered.append(_render(run, line_words, is_last=not words))
        replacements.append((run.pieces[0].lineno, run.pieces[-1].lineno, rendered))
    if not replacements:
        return source
    for start, stop, rendered in sorted(replacements, reverse=True):
        source_lines[start - 1 : stop] = rendered
    return _join_source_lines(source, source_lines)


_Replacement = tuple[int, int, list[str]]


def _prose_runs(tree: ast.Module, source_lines: list[str]) -> Iterator[_Run]:
    """Yields each multi-line string run in `tree` that reads as prose."""
    docstrings = {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
    }
    stack: list[ast.AST] = [tree]
    while stack:
        node = stack.pop()
        if not isinstance(node, ast.Constant | ast.JoinedStr):
            stack.extend(ast.iter_child_nodes(node))
            continue
        if id(node) in docstrings or node.end_lineno == node.lineno:
            continue
        run = _read_run(node, source_lines)
        if run is not None and _reads_as_prose(run):
            yield run


def _read_run(
    node: ast.Constant | ast.JoinedStr, source_lines: list[str]
) -> _Run | None:
    """Parses `node` as a run, or returns `None` for any other shape.

    A run holds one plain or f-string piece per line, every piece at the indent
    and in the quote style of the first.
    """
    if isinstance(node, ast.Constant) and not isinstance(node.value, str):
        return None
    end_lineno = node.end_lineno or node.lineno
    indent = _byte_prefix(source_lines[node.lineno - 1], node.col_offset)
    last = source_lines[end_lineno - 1]
    trailer = last[len(_byte_prefix(last, node.end_col_offset or 0)) :]
    pieces: list[_Piece] = []
    quotes: set[str] = set()
    for lineno in range(node.lineno, end_lineno + 1):
        line = source_lines[lineno - 1]
        if lineno == end_lineno:
            line = line[: len(line) - len(trailer)]
        match = _PIECE_PATTERN.fullmatch(line)
        if match is None or match["indent"] != indent:
            return None
        words = _split_words(match["body"], is_f=bool(match["prefix"]))
        if words is None:
            return None
        quotes.add(match["quote"])
        pieces.append(_Piece(lineno, words, match["body"].endswith(" ")))
    if len(quotes) != 1:
        return None
    return _Run(indent, quotes.pop(), tuple(pieces), trailer)


def _byte_prefix(line: str, byte_offset: int) -> str:
    """Returns the text of `line` before the AST's UTF-8 `byte_offset`."""
    return line.encode()[:byte_offset].decode(errors="replace")


_PIECE_PATTERN = re.compile(
    r"(?P<indent>[ \t]*)(?P<prefix>[fF]?)(?P<quote>[\"'])"
    r"(?P<body>(?:[^\\\"'\n]|\\.|(?!(?P=quote))[\"'])*)(?P=quote)"
)


def _split_words(body: str, *, is_f: bool) -> tuple[_Word, ...] | None:
    """Splits one piece's body at its spaces, keeping placeholders whole.

    A double, leading, or trailing space yields an empty word, which the prose
    test rejects. Returns `None` for an f-string whose braces do not balance.
    """
    segments = _segments(body, is_f=is_f)
    if segments is None:
        return None
    words: list[_Word] = []
    current: list[_Segment] = []
    for is_placeholder, text in segments:
        if is_placeholder:
            current.append((True, text))
            continue
        head, *rest = text.split(" ")
        if head:
            current.append((False, head))
        for part in rest:
            words.append(_Word(tuple(current)))
            current = [(False, part)] if part else []
    if current:
        words.append(_Word(tuple(current)))
    return tuple(words)


def _segments(body: str, *, is_f: bool) -> tuple[_Segment, ...] | None:
    """Cuts `body` into literal text and placeholders.

    Literal text holds its braces unescaped, so it reads the same whichever
    prefix the piece it lands in takes. Returns `None` when a placeholder never
    closes.
    """
    if not is_f:
        return ((False, body),) if body else ()
    segments: list[_Segment] = []
    literal = ""
    index = 0
    while index < len(body):
        if body.startswith(("{{", "}}"), index):
            literal += body[index]
            index += 2
        elif body[index] != "{":
            literal += body[index]
            index += 1
        else:
            end = _placeholder_end(body, index)
            if end is None:
                return None
            if literal:
                segments.append((False, literal))
                literal = ""
            segments.append((True, body[index:end]))
            index = end
    if literal:
        segments.append((False, literal))
    return tuple(segments)


def _placeholder_end(body: str, start: int) -> int | None:
    """Returns the index just past the placeholder opening at `start`."""
    depth = 0
    for index in range(start, len(body)):
        if body[index] == "{":
            depth += 1
        elif body[index] == "}":
            depth -= 1
            if depth == 0:
                return index + 1
    return None


def _reads_as_prose(run: _Run) -> bool:
    """Reports whether the run's breaks and value mark it as prose."""
    if not all(piece.words and piece.has_trailing_space for piece in run.pieces[:-1]):
        return False
    words = run.words
    if not words or not all(word.segments for word in words):
        return False
    literal = " ".join(_literal_text(word) for word in words)
    if _HTML_TAG.search(literal) or "\\n" in literal:
        return False
    return literal.rstrip(_CLOSERS).endswith((".", "!", "?"))


_HTML_TAG = re.compile(r"<[A-Za-z/!]")
_CLOSERS = ")]`'\""


def _first_fault(run: _Run, layout: list[int]) -> Violation:
    """Builds the violation for the first line that differs from `layout`."""
    index = next(
        i
        for i, (have, want) in enumerate(zip(run.layout, layout, strict=False))
        if have != want
    )
    if run.layout[index] < layout[index]:
        word = _literal_text(run.pieces[index + 1].words[0])
        message = f"under-wrapped string: '{word}' still fits within {DOC_FILL_COLUMNS} columns; rewrap the run"
    else:
        message = f"string runs past {DOC_FILL_COLUMNS} columns; rewrap the run"
    return Violation(
        run.pieces[index].lineno, len(run.indent) + 1, RS_STRING_FILL, message
    )


def _greedy_layout(run: _Run) -> list[int]:
    """Returns how many words each line of the greedily filled run holds."""
    words = run.words
    layout: list[int] = []
    start = 0
    while start < len(words):
        count = 1
        while start + count < len(words):
            candidate = words[start : start + count + 1]
            is_last = start + count + 1 == len(words)
            width = internal_display_width(_render(run, candidate, is_last=is_last))
            if width > DOC_FILL_COLUMNS:
                break
            count += 1
        layout.append(count)
        start += count
    return layout


def _literal_text(word: _Word) -> str:
    """Returns the text of `word`, with each placeholder kept as written."""
    return "".join(text for _, text in word.segments)


def _render(run: _Run, words: list[_Word], *, is_last: bool) -> str:
    """Renders `words` as one source line of the run."""
    is_f = any(is_placeholder for word in words for is_placeholder, _ in word.segments)
    body = " ".join(
        "".join(
            text
            if is_placeholder or not is_f
            else text.replace("{", "{{").replace("}", "}}")
            for is_placeholder, text in word.segments
        )
        for word in words
    )
    prefix = "f" if is_f else ""
    if is_last:
        return f"{run.indent}{prefix}{run.quote}{body}{run.quote}{run.trailer}"
    return f"{run.indent}{prefix}{run.quote}{body} {run.quote}"


_Segment = tuple[bool, str]


class _Word(NamedTuple):
    segments: tuple[_Segment, ...]
    "Pairs of `(is_placeholder, text)`; literal text holds braces unescaped."


class _Piece(NamedTuple):
    lineno: int
    "1-based source line holding the piece."
    words: tuple[_Word, ...]
    "The words of the piece, with the separating spaces dropped."
    has_trailing_space: bool
    "Whether the piece's body ends on a space, the break a prose run uses."


class _Run(NamedTuple):
    indent: str
    "The leading whitespace every piece shares."
    quote: str
    "The quote character every piece uses."
    pieces: tuple[_Piece, ...]
    "The pieces in source order."
    trailer: str
    "The code following the last piece on its line, such as `,` or `)`."

    @property
    def layout(self) -> list[int]:
        """Returns how many words each source line of the run holds."""
        return [len(piece.words) for piece in self.pieces]

    @property
    def words(self) -> list[_Word]:
        """Returns every word of the run in order."""
        return [word for piece in self.pieces for word in piece.words]
