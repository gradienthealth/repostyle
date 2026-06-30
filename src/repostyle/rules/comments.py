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
are read from the `[tool.repostyle]` table, so a repo expresses its own
ticket shape; with no config the defaults apply.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from repostyle.rules._comments import COMMENT_SUFFIXES, extract_comments
from repostyle.rules._shared import (
    _comment_text,
    _has_sentence_boundary,
    _is_directive_comment,
    _is_prose_comment,
    _join_source_lines,
    _strip_trailing_closers,
    _terminal_punctuation_fault,
    find_pyproject,
)
from repostyle.rules._violation import (
    RS_COMMENT_TAG_FORMAT,
    RS_TERMINAL_PUNCTUATION,
    Violation,
)

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
    for lineno, column, string in _own_line_comments(path, source):
        leading = _LEADING_TOKEN_PATTERN.match(string)
        if leading is None:
            continue
        word, follower = leading.group(1), leading.group(2)
        if not follower and not word.isupper():
            continue
        word = word.upper()
        if word not in allowed and word not in _KNOWN_ALIASES:
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


def _canonical_pattern(tags: tuple[str, ...], ticket_pattern: str) -> re.Pattern[str]:
    """Build the regex a canonical `TAG(TICKET): message` comment matches."""
    tag_group = "|".join(re.escape(tag) for tag in tags)
    return re.compile(rf"^#+\s*(?:{tag_group})\((?:{ticket_pattern})\): \S")


def _own_line_comments(path: Path, source: str) -> Iterator[tuple[int, int, str]]:
    """Yield `(line, column, string)` for each comment that owns its line."""
    for comment in extract_comments(path, source):
        if not comment.is_trailing:
            yield comment.lineno, comment.column, comment.string


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
    table = data.get("tool", {}).get("repostyle", {})
    tags = tuple(table.get("comment-tags", DEFAULT_TAGS))
    pattern = table.get("comment-ticket-pattern", DEFAULT_TICKET_PATTERN)
    return tags, pattern


def check_comment_terminal_punctuation(path: Path, source: str) -> Iterator[Violation]:
    """A prose comment's terminal punctuation must match its shape.

    A single-line comment that is one fragment reads as a label and must
    not end with a period; a comment spanning lines or running more than
    one sentence reads as prose and must end with `.`, `!`, or `?`. A
    tool directive, a coding line, and a commented-out statement are not
    prose and are left alone. The check runs over Python, TOML, and YAML
    comments alike, since a `#` comment reads the same in each.
    """
    if path.suffix not in COMMENT_SUFFIXES:
        return
    for lineno, column, fault in _comment_terminal_faults(path, source):
        yield Violation(
            lineno,
            column + 1,
            RS_TERMINAL_PUNCTUATION,
            _comment_terminal_message(fault),
        )


def fix_comment_terminal_punctuation(
    path: Path, source: str, skip_lines: frozenset[int] = frozenset()
) -> str:
    """Repair each flagged comment's terminal punctuation, the RS030 fix.

    A prose comment missing terminal punctuation gains a trailing `.`; a
    fragment carrying one drops it, including a period sitting before
    trailing closers (`note.)`), so the repair matches what the rule
    flags. A comment whose line is in `skip_lines` is left untouched.
    The fix runs on Python only, though the check spans TOML and YAML
    too. Return the source unchanged when nothing repairs.
    """
    if path.suffix != ".py":
        return source
    source_lines = source.splitlines()
    changed = False
    for lineno, _, fault in _comment_terminal_faults(path, source):
        if lineno in skip_lines:
            continue
        stripped = source_lines[lineno - 1].rstrip()
        if fault == "missing":
            source_lines[lineno - 1] = f"{stripped}."
            changed = True
            continue
        core = _strip_trailing_closers(stripped)
        if core.endswith("."):
            source_lines[lineno - 1] = core[:-1] + stripped[len(core) :]
            changed = True
    return _join_source_lines(source, source_lines) if changed else source


def _comment_terminal_faults(path: Path, source: str) -> Iterator[tuple[int, int, str]]:
    """Yield `(line, column, fault)` for each mispunctuated prose comment.

    Trailing comments and standalone blocks are both covered, so the
    check and its fixer see the same flagged locations. Comments are
    read across Python, TOML, and YAML. The fault is `"missing"` or
    `"extra"`, per the house rule.
    """
    for comment in extract_comments(path, source):
        if not comment.is_trailing:
            continue
        text = _comment_text(comment.string)
        if not _is_prose_comment(text):
            continue
        fault = _terminal_punctuation_fault(text, is_prose=_has_sentence_boundary(text))
        if fault is not None:
            yield comment.lineno, comment.column, fault
    for block in _standalone_comment_blocks(path, source):
        text = " ".join(_comment_text(string) for _, _, string in block)
        if not _is_prose_comment(text):
            continue
        is_prose = len(block) > 1 or _has_sentence_boundary(text)
        fault = _terminal_punctuation_fault(text, is_prose=is_prose)
        if fault is None:
            continue
        last_line, last_column, _ = block[-1]
        yield last_line, last_column, fault


def _comment_terminal_message(fault: str) -> str:
    """Return the fix message for a comment terminal-punctuation `fault`."""
    if fault == "missing":
        return "comment reads as prose; end it with terminal punctuation"
    return "comment reads as a fragment; drop the trailing period"


def _standalone_comment_blocks(
    path: Path, source: str
) -> Iterator[list[tuple[int, int, str]]]:
    """Group own-line comments into adjacent same-column blocks.

    A directive line, a trailing comment, a blank gap, or a column shift
    closes the open block, so each yielded block is one contiguous prose
    comment a reader sees as a paragraph.
    """
    block: list[tuple[int, int, str]] = []
    previous: tuple[int, int] | None = None
    for comment in extract_comments(path, source):
        lineno, column, string = comment.lineno, comment.column, comment.string
        if comment.is_trailing or _is_directive_comment(_comment_text(string)):
            if block:
                yield block
            block, previous = [], None
            continue
        if previous is not None and previous != (lineno - 1, column):
            yield block
            block = []
        block.append((lineno, column, string))
        previous = (lineno, column)
    if block:
        yield block
