"""Shared record types for comment extractors."""

from typing import NamedTuple


class _CommentToken(NamedTuple):
    lineno: int
    """1-based line the comment starts on."""
    column: int
    """0-based column of the leading hash."""
    string: str
    """The comment from its leading hash to the end of the line."""
    is_trailing: bool
    """Whether code or data precedes the comment on its line."""
