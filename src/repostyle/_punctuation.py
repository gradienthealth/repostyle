"""Focused helpers extracted from a larger module."""

from __future__ import annotations

_TRAILING_CLOSERS = ')"'


def terminal_punctuation_fault(text: str, *, is_prose: bool) -> str | None:
    """Classifies a prose unit's terminal punctuation against the house rule.

    Args:
        text: The prose or label to classify.
        is_prose: Whether the text must carry terminal punctuation.

    Returns:
        `"missing"` or `"extra"` for a fault, otherwise `None`.
    """
    stripped = strip_trailing_closers(text)
    if not stripped or stripped.endswith(":"):
        return None
    if "://" in stripped.rsplit(maxsplit=1)[-1]:
        return None
    if is_prose:
        return None if stripped[-1] in ".!?" else "missing"
    return "extra" if stripped[-1] == "." else None


def strip_trailing_closers(text: str) -> str:
    """Returns `text` without trailing whitespace or sentence-closing marks."""
    return text.rstrip().rstrip(_TRAILING_CLOSERS)
