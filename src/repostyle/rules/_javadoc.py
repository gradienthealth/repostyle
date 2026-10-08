"""Segments Javadoc comments into the prose units the doc rules grade.

A Javadoc comment is HTML behind a `*` gutter. Its first paragraph is the
summary, a `<p>` opens a later paragraph, an `<li>` opens a bullet, and the
block tags (`@param`, `@return`, `@throws`, ...) close the description. An
inline tag that carries code -- `{@code x}`, `{@link Foo#bar}`, or a `<code>`
element -- reads as a backtick code span in a unit's text, so the prose helpers
that already skip backtick spans skip it too, and `<pre>` blocks hold no prose.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import NamedTuple

from repostyle.languages import JavaToken, lex_java
from repostyle.rules._prose_sources import InternalDocLine
from repostyle.rules._prose_units import InternalProseUnit


class InternalJavadoc(NamedTuple):
    lineno: int
    """1-based line of the comment's opening `/**`."""
    col: int
    """1-based column of the comment's opening `/**`."""
    units: tuple[InternalProseUnit, ...]
    """The comment's summary, body, bullet, and `tag` units in order."""
    prose_lines: dict[int, str]
    """Each comment line, full width, with every non-prose column blanked."""
    text_ends: dict[int, int]
    """Each comment line's column just past its last non-blank character."""


def internal_javadoc_comments(source: str) -> Iterator[InternalJavadoc]:
    """Yields each Javadoc comment in Java `source`, segmented into units."""
    source_lines = source.splitlines()
    for token in lex_java(source):
        if token.kind == "doc_comment":
            yield internal_javadoc(token, source_lines)


def internal_tag_caption_end(text: str) -> int:
    """Returns the offset in a block-tag line where its description starts.

    The caption is the tag itself plus, for `@param`, `@throws`, and
    `@exception`, the name it documents, which is code rather than prose.
    """
    match = _TAG_CAPTION_PATTERN.match(text)
    return match.end() if match is not None else 0


_TAG_CAPTION_PATTERN = re.compile(r"@(?:param|throws|exception)\s+\S+|@\w+")


def internal_javadoc(token: JavaToken, source_lines: list[str]) -> InternalJavadoc:
    """Builds the segmented record of one Javadoc `token`."""
    lines = _doc_lines(token, source_lines)
    segmenter = _JavadocSegmenter()
    for line in lines:
        segmenter.consume(line)
    segmenter.close()
    return InternalJavadoc(
        token.line,
        token.column + 1,
        tuple(segmenter.units),
        _prose_lines(lines, source_lines),
        {line.lineno: line.column + len(line.text) for line in lines},
    )


class _JavadocSegmenter:
    """Groups Javadoc lines into summary, body, bullet, and tag units.

    Feed lines in order with `consume`, call `close` after the last, then read
    `units`. A blank line or `<p>` ends a paragraph, an `<li>`, `<dt>`, or
    `<dd>` opens a bullet that later lines extend until the next item or list
    end, a `<pre>` block, table, or heading yields nothing, and a block tag
    opens a `tag` unit that every following line extends until the next tag,
    since block tags end the description.
    """

    def __init__(self) -> None:
        self.units: list[InternalProseUnit] = []
        self._open: list[InternalDocLine] = []
        self._open_kind = "summary"
        self._summary_done = False
        self._closing_tag = ""
        self._in_tags = False

    def close(self) -> None:
        """Finishes the open unit, appending it to `units` if it has prose."""
        if not self._open:
            return
        kind = self._open_kind
        if kind == "summary":
            self._summary_done = True
        text = _unit_text(" ".join(line.text for line in self._open))
        last = self._open[-1]
        linenos = tuple(line.lineno for line in self._open)
        self._open = []
        if text:
            self.units.append(
                InternalProseUnit(kind, last.lineno, last.column + 1, text, linenos)
            )

    def consume(self, line: InternalDocLine) -> None:
        """Routes `line` to its unit, ending the open unit as needed."""
        text = line.text
        if self._consume_verbatim(text):
            return
        if _BLOCK_TAG_PATTERN.match(text):
            self._in_tags = True
            self._start(line, "tag")
        elif self._in_tags:
            self._extend(line)
        elif not text or _LIST_BOUNDARY_PATTERN.match(text):
            self.close()
        elif text.startswith(_ITEM_OPENERS):
            self._start(line, "bullet")
        elif text.startswith("<p>"):
            self._start(line, "body")
        elif self._open:
            self._open.append(line)
        else:
            self._start(line, "body" if self._summary_done else "summary")

    def _consume_verbatim(self, text: str) -> bool:
        """Tracks a block holding no prose, reporting whether `text` is in one.

        A `<pre>` block holds code, a `<table>` holds cells rather than
        sentences, and a heading is a label; each runs to its closing tag.
        """
        if self._closing_tag:
            if self._closing_tag in text.lower():
                self._closing_tag = ""
            return True
        match = _VERBATIM_OPENER_PATTERN.match(text)
        if match is None:
            return False
        self.close()
        closing = f"</{match.group(1).lower()}>"
        if closing not in text.lower():
            self._closing_tag = closing
        return True

    def _extend(self, line: InternalDocLine) -> None:
        """Adds a non-blank `line` to the open tag unit."""
        if line.text:
            self._open.append(line)

    def _start(self, line: InternalDocLine, kind: str) -> None:
        """Closes the open unit and opens a `kind` unit at `line`."""
        self.close()
        self._open = [line]
        self._open_kind = kind


_BLOCK_TAG_PATTERN = re.compile(r"@[a-zA-Z]+\b")


_VERBATIM_OPENER_PATTERN = re.compile(r"<(pre|table|h[1-6])\b", re.IGNORECASE)


_ITEM_OPENERS = ("<li>", "<dt>", "<dd>")


_LIST_BOUNDARY_PATTERN = re.compile(r"</?(?:ul|ol|dl|blockquote)>\s*$")


def _unit_text(text: str) -> str:
    """Rewrites Javadoc markup in `text` into plain prose with code spans.

    A code-carrying inline tag or `<code>` element becomes a backtick span of
    its content, any other inline tag keeps its content as prose, an HTML tag
    drops, and an entity becomes the character it names.
    """
    text = _CODE_ELEMENT_PATTERN.sub(lambda match: f"`{match.group(1)}`", text)
    text = _INLINE_TAG_CONTENT_PATTERN.sub(_inline_tag_text, text)
    text = _HTML_TAG_PATTERN.sub("", text)
    for entity, character in _ENTITIES.items():
        text = text.replace(entity, character)
    return " ".join(text.split())


def _inline_tag_text(match: re.Match[str]) -> str:
    """Returns the prose an inline tag reads as."""
    tag, content = match.group(1), match.group(2).strip()
    if tag in _CODE_TAGS:
        return f"`{content}`"
    return content


_CODE_TAGS = frozenset({"code", "link", "linkplain", "literal", "value"})


_CODE_ELEMENT_PATTERN = re.compile(r"<code>(.*?)</code>")


_INLINE_TAG_CONTENT_PATTERN = re.compile(r"\{@(\w+)((?:[^{}]|\{[^{}]*\})*)\}")


_HTML_TAG_PATTERN = re.compile(r"</?[A-Za-z][^>]*>")


_ENTITIES = {"&lt;": "<", "&gt;": ">", "&amp;": "&", "&mdash;": "—", "&nbsp;": " "}


def _doc_lines(token: JavaToken, source_lines: list[str]) -> list[InternalDocLine]:
    """Splits a Javadoc token into gutter-stripped, position-tagged lines.

    Each line's text starts after the `/**` opener or the `*` gutter and ends
    before the `*/` closer, so a column indexes the source line itself. The
    relative indent counts the spaces past the gutter's single separator, the
    indent google-java-format gives a wrapped block-tag continuation.
    """
    lines: list[InternalDocLine] = []
    for offset in range(token.end_line - token.line + 1):
        lineno = token.line + offset
        line = source_lines[lineno - 1]
        start = token.column + 3 if offset == 0 else _gutter_end(line)
        end = len(line)
        if lineno == token.end_line:
            end = _token_end(token) - 2
        body = line[start:end]
        text = body.strip()
        column = start + len(body) - len(body.lstrip())
        relative = max(0, len(body) - len(body.lstrip()) - 1) if text else 0
        lines.append(InternalDocLine(lineno, column, relative, text))
    return lines


def _gutter_end(line: str) -> int:
    """Returns the column just past a continuation line's `*` gutter."""
    stripped = line.lstrip()
    start = len(line) - len(stripped)
    if stripped.startswith("*") and not stripped.startswith("*/"):
        return start + 1
    return start


def _prose_lines(
    lines: list[InternalDocLine], source_lines: list[str]
) -> dict[int, str]:
    """Returns each comment line with every non-prose column blanked.

    The gutter, the delimiters, a whole `{@code ...}` or `{@link ...}` tag, and
    every HTML tag and entity become spaces, so an offset into the result is an
    offset into the source line. The comment is blanked as one text, so an
    inline tag that google-java-format wrapped across lines is blanked whole.
    """
    regions = [_blank_outside(source_lines[line.lineno - 1], line) for line in lines]
    blanked = _MARKUP_PATTERN.sub(_spaces, "\n".join(regions))
    return dict(zip((line.lineno for line in lines), blanked.split("\n"), strict=True))


def _blank_outside(line: str, doc_line: InternalDocLine) -> str:
    """Blanks every column of `line` outside the doc line's own text."""
    start = doc_line.column
    end = start + len(doc_line.text)
    return " " * start + line[start:end] + " " * (len(line) - end)


def _spaces(match: re.Match[str]) -> str:
    """Returns `match` with every character but a line break made a space."""
    return re.sub(r"[^\n]", " ", match.group())


_MARKUP_PATTERN = re.compile(
    r"\{@\w+(?:[^{}]|\{[^{}]*\})*\}|<code>.*?</code>|</?[A-Za-z][^>]*>|&[#\w]+;",
    re.DOTALL,
)


def _token_end(token: JavaToken) -> int:
    """Returns the column just past a token's last character on its last line.

    Code or another comment can follow a Javadoc's `*/` on the same line, so
    the comment ends where its token does, not at the line's last `*/`.
    """
    if token.line == token.end_line:
        return token.column + len(token.text)
    return len(token.text.rsplit("\n", 1)[-1])
