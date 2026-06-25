"""Comment-tag format rule (RS022): standardize special comments.

A special comment carries one of a small set of tags and points at a
tracking ticket, so an agent reading the finding learns the canonical
form rather than guessing one. The canonical form is `TAG(TICKET):
message`, where the tag is one of a configured allowed set (`TODO`,
`FIXME`, `NOTE`, `HACK` by default) and the ticket matches a configured
pattern (the Linear-id shape `[A-Z]+-\\d+`, plus the literal `NO-ISSUE`,
by default).

A comment whose leading token looks like a tag but deviates is flagged:
a tag outside the allowed set (`XXX`, `BUG`), wrong casing (`# todo`),
missing parentheses (`TODO PROC-1`), a missing ticket (`TODO: fix`), a
name instead of a ticket (`TODO(sai)`), or a wrong separator after the
parenthesized ticket. Both the allowed tag set and the ticket pattern
are read from the `[tool.pystyle]` table, so a repo expresses its own
ticket shape; with no config the defaults apply.
"""

from __future__ import annotations

import io
import re
import tokenize
import tomllib
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from pystyle.rules._shared import find_pyproject
from pystyle.rules._violation import RS_COMMENT_TAG_FORMAT, Violation

DEFAULT_TAGS = ("TODO", "FIXME", "NOTE", "HACK")
DEFAULT_TICKET_PATTERN = r"[A-Z]+-\d+|NO-ISSUE"

# Tags an author commonly reaches for that the canonical set replaces,
# so a deviation is steered toward an allowed tag rather than silently
# accepted. A token matching the leading-token shape but on neither this
# set nor the allowed set is ordinary prose and never flagged.
_KNOWN_ALIASES = frozenset({"XXX", "BUG", "TBD", "OPTIMIZE", "REVIEW", "WIP"})

# A comment's first token, with the character that immediately follows
# it captured separately. A tag is used tag-style — written in all caps
# (`TODO fix`) or set off by a `(` or `:` separator (`todo: x`,
# `Note(...)`); a title-case word trailed by prose (`Note that this
# works`) is an ordinary sentence. The follower tells the two apart. The
# token is letters only, so a word carrying digits or punctuation stays
# prose.
_LEADING_TOKEN_PATTERN = re.compile(r"^#+\s*([A-Za-z]+)([(:]?)")


def check_comment_tag_format(path: Path, source: str) -> Iterator[Violation]:
    """A special comment must read `TAG(TICKET): message`.

    A comment opening with a tag — a token that is an allowed tag or a
    known alias of one, and is used tag-style: written in all caps or
    set off by a `(` or `:` separator — is held to the canonical form:
    an allowed tag, the ticket in parentheses matching the configured
    pattern, then `: ` and a message. A deviation — an unknown tag,
    wrong casing, a missing or malformed ticket, or a wrong separator —
    is flagged. A title-case word trailed by prose is an ordinary
    sentence and is left alone. The allowed tags and ticket pattern come
    from config.
    """
    if path.suffix != ".py":
        return
    tags, ticket_pattern = _resolve_config(path)
    allowed = {tag.upper() for tag in tags}
    canonical = _canonical_pattern(tags, ticket_pattern)
    for token in _own_line_comments(source):
        leading = _LEADING_TOKEN_PATTERN.match(token.string)
        if leading is None:
            continue
        word, follower = leading.group(1), leading.group(2)
        if not follower and not word.isupper():
            continue
        word = word.upper()
        if word not in allowed and word not in _KNOWN_ALIASES:
            continue
        if canonical.match(token.string):
            continue
        line, column = token.start
        canonical_tag = next(iter(tags)) if word in _KNOWN_ALIASES else word
        yield Violation(
            line,
            column + 1,
            RS_COMMENT_TAG_FORMAT,
            f"comment tag is not canonical; write '{canonical_tag}(TICKET): "
            "message' with an allowed tag and a ticket matching the configured "
            "pattern",
        )


def _canonical_pattern(tags: tuple[str, ...], ticket_pattern: str) -> re.Pattern[str]:
    """Build the regex a canonical `TAG(TICKET): message` comment matches."""
    tag_group = "|".join(re.escape(tag) for tag in tags)
    return re.compile(rf"^#+\s*(?:{tag_group})\((?:{ticket_pattern})\): \S")


def _own_line_comments(source: str) -> Iterator[tokenize.TokenInfo]:
    """Yield comment tokens, skipping those trailing code on their line."""
    source_lines = source.splitlines()
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except tokenize.TokenError:
        return
    for token in tokens:
        if token.type != tokenize.COMMENT:
            continue
        line, column = token.start
        if source_lines[line - 1][:column].strip():
            continue
        yield token


def _resolve_config(path: Path) -> tuple[tuple[str, ...], str]:
    """Return the allowed tags and ticket pattern for `path`'s repo."""
    pyproject = find_pyproject(path)
    if pyproject is None:
        return DEFAULT_TAGS, DEFAULT_TICKET_PATTERN
    return _comment_tag_config(pyproject)


@lru_cache(maxsize=128)
def _comment_tag_config(pyproject: Path) -> tuple[tuple[str, ...], str]:
    """Read the allowed tags and ticket pattern from a pyproject file.

    Return the configured allowed tag tuple and ticket-pattern regex,
    each falling back to its default when the table omits it.
    """
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return DEFAULT_TAGS, DEFAULT_TICKET_PATTERN
    table = data.get("tool", {}).get("pystyle", {})
    tags = tuple(table.get("comment-tags", DEFAULT_TAGS))
    pattern = table.get("comment-ticket-pattern", DEFAULT_TICKET_PATTERN)
    return tags, pattern
