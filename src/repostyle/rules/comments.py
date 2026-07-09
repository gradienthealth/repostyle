"""Comment rules (RS022, RS038, RS030): tag format, indent, punctuation.

RS022 standardizes special comments. A special comment carries one of a small
set of tags and points at a tracking ticket, so an agent reading the finding
learns the canonical form rather than guessing one. The canonical form is
`TAG(TICKET): message`, where the tag is one of a configured allowed set
(`TODO`, `FIXME`, `NOTE`, `HACK` by default) and the ticket matches a
configured pattern (the Linear-id shape `[A-Z]+-\\d+`, plus the literal
`NO-ISSUE`, by default).

A comment whose leading token looks like a tag but deviates is flagged: a tag
outside the allowed set (`XXX`, `BUG`), wrong casing (`# todo`), missing
parentheses (`TODO PROC-1`), a missing ticket (`TODO: fix`), a name instead of
a ticket (`TODO(sai)`), or a wrong separator after the parenthesized ticket.
Both the allowed tag set and the ticket pattern are read from the
`[tool.repostyle]` table, so a repo expresses its own ticket shape; with no
config the defaults apply.

RS038 keeps a wrapped tag comment readable as one unit: a continuation line of
a `TODO(TICKET): ...` comment is indented past the tag, so the wrapped text
reads as subordinate to it. A contiguous run of `#` comments at one column is
the unit, so an independent note is set off by a blank line rather than folded
into the tag.

RS030 holds a comment to the house terminal-punctuation rule: a prose comment
ends with terminal punctuation, while a single-line fragment does not. The
check spans Python, TOML, and YAML comments alike, and its `--fix` half repairs
Python comments in place.
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
    _is_prose_comment,
    _join_source_lines,
    _standalone_comment_blocks,
    _strip_trailing_closers,
    _terminal_punctuation_fault,
    find_pyproject,
)
from repostyle.rules._violation import (
    RS_COMMENT_TAG_FORMAT,
    RS_TAG_COMMENT_CONTINUATION_INDENT,
    RS_TERMINAL_PUNCTUATION,
    Violation,
)

DEFAULT_TAGS = ("TODO", "FIXME", "NOTE", "HACK")
DEFAULT_TICKET_PATTERN = r"[A-Z]+-\d+|NO-ISSUE"

# Tags an author commonly reaches for that the canonical set replaces, so a
# deviation is steered toward an allowed tag rather than silently accepted. A
# token matching the leading-token shape but on neither this set nor the
# allowed set is ordinary prose and never flagged.
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

    A comment opening with a tag — a token that is an allowed tag or a known
    alias of one, and is used tag-style: written in all caps or set off by a
    `(` or `:` separator — is held to the canonical form: an allowed tag, the
    ticket in parentheses matching the configured pattern, then `: ` and a
    message. A deviation — an unknown tag, wrong casing, a missing or malformed
    ticket, or a wrong separator — is flagged. A title-case word trailed by
    prose is an ordinary sentence and is left alone. The allowed tags and
    ticket pattern come from config. The check runs over Python, TOML, and YAML
    comments alike, since a `#` comment reads the same in each.
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
    Python, TOML, and YAML comments alike, since a `#` comment reads the same
    in each.
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
    return re.compile(rf"^#+\s*(?:{tag_group})\((?:{ticket_pattern})\): \S")


def _comment_text_column(string: str) -> int:
    """Returns the column of a comment's text past its opening `#`.

    Counts the hashes and expands tabs, so a deeper hash run or a tab reads as
    more indent than a single space.
    """
    body = string.lstrip("#")
    hashes = len(string) - len(body)
    indent = body.removesuffix(body.lstrip())
    return hashes + len(indent.expandtabs())


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
    pyproject = find_pyproject(path)
    if pyproject is None:
        return DEFAULT_TAGS, DEFAULT_TICKET_PATTERN
    return _comment_tag_config(pyproject)


@lru_cache(maxsize=128)
def _comment_tag_config(pyproject: Path) -> tuple[tuple[str, ...], str]:
    """Reads the allowed tags and ticket pattern from a pyproject file.

    Returns the configured allowed tag tuple and ticket-pattern regex, each
    falling back to its default when the table omits it.
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

    A single-line comment that is one fragment reads as a label and must not
    end with a period; a comment spanning lines or running more than one
    sentence reads as prose and must end with `.`, `!`, or `?`. A tool
    directive, a coding line, and a commented-out statement are not prose and
    are left alone. The check runs over Python, TOML, and YAML comments alike,
    since a `#` comment reads the same in each.
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
    """Repairs each flagged comment's terminal punctuation, the RS030 fix.

    A prose comment missing terminal punctuation gains a trailing `.`; a
    fragment carrying one drops it, including a period sitting before trailing
    closers (`note.)`), so the repair matches what the rule flags. A comment
    whose line is in `skip_lines` is left untouched. The fix runs on Python
    only, though the check spans TOML and YAML too.

    Returns:
        The source with each flagged comment's terminal punctuation repaired,
        unchanged when nothing repairs.
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
    """Yields `(line, column, fault)` for each mispunctuated prose comment.

    Trailing comments and standalone blocks are both covered, so the check and
    its fixer see the same flagged locations. Comments are read across Python,
    TOML, and YAML. The fault is `"missing"` or `"extra"`, per the house rule.
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
    """Returns the violation message for a terminal-punctuation `fault`."""
    if fault == "missing":
        return "comment reads as prose; end it with terminal punctuation"
    return "comment reads as a fragment; drop the trailing period"
