"""Focused helpers extracted from a larger module."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from repostyle.languages import COMMENT_SUFFIXES, extract_comments
from repostyle.rules._violation import (
    RS_BANNER_COMMENT,
    Violation,
)
from repostyle.rules.comment_tags import (
    DEFAULT_TAGS as DEFAULT_TAGS,
)
from repostyle.rules.comment_tags import (
    DEFAULT_TICKET_PATTERN as DEFAULT_TICKET_PATTERN,
)
from repostyle.rules.comment_tags import (
    check_comment_tag_format as check_comment_tag_format,
)
from repostyle.rules.comment_tags import (
    check_tag_comment_continuation_indent as check_tag_comment_continuation_indent,
)

_BANNER_CHARACTERS = frozenset("-=#*~_+")

_TABLE_BORDER_PATTERN = re.compile(r"\+[-=+]*\+")

_FRAMED_TITLE_PATTERN = re.compile(r"^[-=*~_+]{3,}\s|\s[-=*~_+]{3,}$")

_CODING_DECLARATION_PATTERN = re.compile(r"^-\*-\s.*coding[:=].*\s-\*-$")


def check_banner_comment(path: Path, source: str) -> Iterator[Violation]:
    """Flags a banner, section-divider, or framed-title comment.

    A standalone comment drawn out of rule characters -- a bare `# -----`
    divider, the frame lines boxing a `# TESTS` title, or a one-line framed
    title like `# --- main ---` -- decorates a grouping the code should express
    with structure. A divider is styled differently by every author and every
    file, so the set is banned outright rather than held to one canonical
    shape; each frame line of a boxed banner draws its own violation.

    A comment is a banner when its text is wholly rule characters, or when a
    run of three or more opens or closes it against whitespace. Bounding the
    run on the title side spares an ASCII scissors (`---8<---`) and an arrow
    (`----->`), whose runs abut their content. A run shorter than four
    characters standing alone is left alone too, sparing YAML's commented-out
    `# ---` document separator, as are the `+----+` ASCII-table border RS009
    already treats as verbatim content, PEP 263's `-*- coding: utf-8 -*-`
    declaration, and a trailing comment. The check runs over Python, TOML,
    YAML, and shell comments alike.
    """
    if path.suffix not in COMMENT_SUFFIXES:
        return
    for comment in extract_comments(path, source):
        if comment.is_trailing:
            continue
        text = comment.string[1:].strip()
        if not _is_banner_text(text):
            continue
        yield Violation(
            comment.lineno,
            comment.column + 1,
            RS_BANNER_COMMENT,
            "banner comment; delete the divider and express the grouping with "
            "structure -- split the file, gather the section into a class "
            "(test functions into a test class), or open the run with a "
            "sentence comment",
        )


def _is_banner_text(text: str) -> bool:
    """Reports whether a comment's text is a divider or a framed title.

    `text` is the comment with its leading hash stripped and stripped of
    surrounding whitespace.
    """
    if _CODING_DECLARATION_PATTERN.match(text):
        return False
    if not set(text) - _BANNER_CHARACTERS:
        return len(text) >= 4 and not _TABLE_BORDER_PATTERN.fullmatch(text)
    return bool(_FRAMED_TITLE_PATTERN.search(text))
