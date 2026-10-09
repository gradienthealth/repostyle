"""Focused helpers extracted from a larger rule module."""

from __future__ import annotations

import re
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from repostyle._shared import (
    _comment_text,
    _repostyle_table,
    _standalone_comment_blocks,
    find_config_file,
)
from repostyle.languages import (
    COMMENT_SUFFIXES,
    MARKER_PATTERN,
    comment_marker,
    extract_comments,
)
from repostyle.rules._violation import (
    RS_COMMENT_TAG_FORMAT,
    RS_TAG_COMMENT_CONTINUATION_INDENT,
    Violation,
)

DEFAULT_TAGS = ("TODO", "FIXME", "NOTE", "HACK")
DEFAULT_TICKET_PATTERN = r"[A-Z]+-\d+|NO-ISSUE"
_KNOWN_ALIASES = frozenset({"XXX", "BUG", "TBD", "OPTIMIZE", "REVIEW", "WIP"})
_LEADING_TOKEN_PATTERN = re.compile(
    rf"^(?:{MARKER_PATTERN.pattern})\s*([A-Za-z]+)([(:]?)"
)


def check_comment_tag_format(path: Path, source: str) -> Iterator[Violation]:
    """A special comment must read `TAG(TICKET): message`.

    A comment opening with a tag -- a token that is an allowed tag or a known
    alias of one, and is used tag-style: written in all caps or set off by a
    `(` or `:` separator -- is held to the canonical form: an allowed tag, the
    ticket in parentheses matching the configured pattern, then `: ` and a
    message. A deviation -- an unknown tag, wrong casing, a missing or
    malformed ticket, or a wrong separator -- is flagged. A title-case word
    trailed by prose is an ordinary sentence and is left alone. The allowed
    tags and ticket pattern come from config. The check runs over Python, TOML,
    and YAML comments alike, since a `#` comment reads the same in each.
    """
    if path.suffix not in COMMENT_SUFFIXES:
        return
    tags, ticket_pattern = _resolve_config(path)
    # No configured tags means no canonical form to steer a deviation toward
    if not tags:
        return
    allowed = {tag.upper() for tag in tags}
    canonical = _canonical_pattern(tags, ticket_pattern)
    for lineno, column, string in _own_line_comments(path, source):
        word = _leading_tag(string, allowed)
        if word is None:
            continue
        if canonical.match(string):
            continue
        canonical_tag = next(iter(tags)) if word in _KNOWN_ALIASES else word
        yield Violation(
            lineno,
            column + 1,
            RS_COMMENT_TAG_FORMAT,
            f"comment tag is not canonical; write '{canonical_tag}(TICKET): "
            "message' with an allowed tag and a ticket matching the configured "
            "pattern",
        )


def check_tag_comment_continuation_indent(
    path: Path, source: str
) -> Iterator[Violation]:
    """A wrapped tag comment indents its continuation past the tag.

    A tag comment (`TODO(TICKET): ...` and the other RS022 tags) that runs onto
    a further line reads as one unit only when the wrapped text is indented
    past the tag, so a flush continuation line is flagged. A contiguous run of
    `#` comments at one column is the unit: a blank line or a differing column
    starts a separate one, so an independent note is set off by a blank line
    rather than folded into the tag. A continuation that is itself a tag
    comment is a new tag, not a wrap, and is left alone. The check runs over
    Python, TOML, YAML, and shell comments alike, since a `#` comment reads the
    same in each.
    """
    if path.suffix not in COMMENT_SUFFIXES:
        return
    tags, _ = _resolve_config(path)
    allowed = {tag.upper() for tag in tags}
    for block in _standalone_comment_blocks(path, source):
        if len(block) < 2 or _leading_tag(block[0][2], allowed) is None:
            continue
        base_column = _comment_text_column(block[0][2])
        for lineno, column, string in block[1:]:
            if not _comment_text(string) or _leading_tag(string, allowed):
                continue
            if _comment_text_column(string) <= base_column:
                yield Violation(
                    lineno,
                    column + 1,
                    RS_TAG_COMMENT_CONTINUATION_INDENT,
                    "tag-comment continuation is not indented past the tag; "
                    "indent it, or set it off with a blank line if it is a new "
                    "comment",
                )


def _canonical_pattern(tags: tuple[str, ...], ticket_pattern: str) -> re.Pattern[str]:
    """Builds the regex a canonical `TAG(TICKET): message` comment matches."""
    tag_group = "|".join(re.escape(tag) for tag in tags)
    return re.compile(
        rf"^(?:{MARKER_PATTERN.pattern})\s*(?:{tag_group})\((?:{ticket_pattern})\): \S"
    )


def _comment_text_column(string: str) -> int:
    """Returns the column of a comment's text past its opening marker.

    Counts the marker and expands tabs, so a deeper marker run or a tab reads
    as more indent than a single space.
    """
    marker = comment_marker(string)
    body = string[len(marker) :]
    indent = body.removesuffix(body.lstrip())
    return len(marker) + len(indent.expandtabs())


def _leading_tag(string: str, allowed: set[str]) -> str | None:
    """Returns a comment's leading tag uppercased, or `None` if it has none.

    A tag is a leading token in `allowed` or a known alias, used tag-style:
    written in all caps or set off by a `(` or `:` separator.
    """
    leading = _LEADING_TOKEN_PATTERN.match(string)
    if leading is None:
        return None
    word, follower = leading.group(1), leading.group(2)
    if not follower and not word.isupper():
        return None
    word = word.upper()
    return word if word in allowed or word in _KNOWN_ALIASES else None


def _own_line_comments(path: Path, source: str) -> Iterator[tuple[int, int, str]]:
    """Yields `(line, column, string)` for each comment that owns its line."""
    for comment in extract_comments(path, source):
        if not comment.is_trailing:
            yield comment.lineno, comment.column, comment.string


def _resolve_config(path: Path) -> tuple[tuple[str, ...], str]:
    """Returns the allowed tags and ticket pattern for the repo of `path`."""
    pyproject = find_config_file(path)
    if pyproject is None:
        return DEFAULT_TAGS, DEFAULT_TICKET_PATTERN
    return _comment_tag_config(pyproject)


@lru_cache(maxsize=128)
def _comment_tag_config(pyproject: Path) -> tuple[tuple[str, ...], str]:
    """Reads the allowed tags and ticket pattern from a pyproject file.

    Returns the configured allowed tag tuple and ticket-pattern regex, each
    falling back to its default when the table omits it.
    """
    table = _repostyle_table(pyproject)
    tags = tuple(table.get("comment-tags", DEFAULT_TAGS))
    pattern = table.get("comment-ticket-pattern", DEFAULT_TICKET_PATTERN)
    return tags, pattern
