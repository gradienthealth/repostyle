"""The languages repostyle reads, and the syntax each one exposes to rules.

Knowledge of one language's syntax -- how its comments are written, which spans
a block directive covers, where its tests live -- sits in this package behind a
`Language` record, so a new language arrives as one module and one registered
record rather than as edits across the rules.
"""

from repostyle.languages._model import (
    CommentToken,
    Language,
    comment_at,
    comment_text,
)
from repostyle.languages._python import parse_python
from repostyle.languages._registry import (
    COMMENT_SUFFIXES,
    LANGUAGES,
    LINTABLE_SUFFIXES,
    MARKDOWN,
    PYTHON,
    SHELL,
    TOML,
    YAML,
    block_spans,
    extract_comments,
    extract_folded_runs,
    language_for,
)

__all__ = [
    "COMMENT_SUFFIXES",
    "LANGUAGES",
    "LINTABLE_SUFFIXES",
    "MARKDOWN",
    "PYTHON",
    "SHELL",
    "TOML",
    "YAML",
    "CommentToken",
    "Language",
    "block_spans",
    "comment_at",
    "comment_text",
    "extract_comments",
    "extract_folded_runs",
    "language_for",
    "parse_python",
]
