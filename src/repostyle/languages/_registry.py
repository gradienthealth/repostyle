"""The registered languages and the per-file dispatch over their hooks."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from repostyle.languages._java import is_java_test_file, java_block_spans, java_comments
from repostyle.languages._model import CommentToken, Language
from repostyle.languages._python import (
    is_python_test_file,
    python_block_spans,
    python_comments,
)
from repostyle.languages._shell import shell_comments
from repostyle.languages._toml import toml_comments
from repostyle.languages._yaml import folded_runs, folded_scalars, yaml_comments

PYTHON = Language(
    "python",
    frozenset({".py"}),
    is_default=True,
    comments=python_comments,
    block_spans=python_block_spans,
    is_test_file=is_python_test_file,
    has_identifier_filenames=True,
)

MARKDOWN = Language("markdown", frozenset({".md"}), is_default=True)

TOML = Language("toml", frozenset({".toml"}), is_default=True, comments=toml_comments)


def _yaml_block_spans(source: str) -> tuple[tuple[int, int], ...]:
    """Returns each folded scalar's inclusive span, from introducer to end.

    A span runs from the `>` introducer line through the scalar's last content
    line, so a suppression directive written above or trailing the introducer
    reaches the prose inside.
    """
    return tuple((introducer + 1, stop) for introducer, stop in folded_scalars(source))


YAML = Language(
    "yaml",
    frozenset({".yaml", ".yml"}),
    is_default=True,
    comments=yaml_comments,
    block_spans=_yaml_block_spans,
)

SHELL = Language("shell", frozenset({".sh"}), is_default=True, comments=shell_comments)

# Opt-in while its rules settle: a repo lints Java only by listing it under
# `languages`, so a release adding Java checks reaches no repo unasked.
JAVA = Language(
    "java",
    frozenset({".java"}),
    is_default=False,
    comments=java_comments,
    block_spans=java_block_spans,
    is_test_file=is_java_test_file,
    fill_columns=100,
    has_identifier_filenames=True,
)

LANGUAGES: tuple[Language, ...] = (PYTHON, MARKDOWN, TOML, YAML, SHELL, JAVA)

DEFAULT_LANGUAGES = frozenset(
    language.name for language in LANGUAGES if language.is_default
)

_BY_SUFFIX = {
    suffix: language for language in LANGUAGES for suffix in language.suffixes
}

# The suffixes whose files carry line comments: every comment rule's reach
COMMENT_SUFFIXES = frozenset(
    suffix
    for language in LANGUAGES
    if language.comments is not None
    for suffix in language.suffixes
)

LINTABLE_SUFFIXES = frozenset(_BY_SUFFIX)


# Cache on (path, source) so a file is scanned once and the result shared
# across the rules that read it and the suppression parser. A tuple is returned
# so the cached value is safe to iterate repeatedly.
@lru_cache(maxsize=128)
def extract_comments(path: Path, source: str) -> tuple[CommentToken, ...]:
    """Returns each line comment in `source`, scanned by its file's language.

    Each scanner is string-aware, so a comment marker inside a string, a
    multi-line string, a YAML block scalar, or a shell heredoc is not mistaken
    for a comment. The scans are conservative: an unrecognised construct keeps
    its marker out of the results rather than risk flagging string content.

    Returns:
        Each comment in source order, and nothing at all for a file whose
        language has no comments or that no language claims.
    """
    language = language_for(path)
    if language is None or language.comments is None:
        return ()
    return tuple(language.comments(source))


@lru_cache(maxsize=128)
def block_spans(path: Path, source: str) -> tuple[tuple[int, int], ...]:
    """Returns the sorted inclusive line span of every block in `source`.

    A block is whatever the file's language lets a block directive cover: a
    statement in Python and a folded scalar in YAML. A language without such
    blocks, or a source that does not parse, has none.
    """
    language = language_for(path)
    if language is None:
        return ()
    return tuple(sorted(language.block_spans(source)))


@lru_cache(maxsize=128)
def extract_folded_runs(path: Path, source: str) -> tuple[tuple[int, ...], ...]:
    """Returns the rewrappable runs of the YAML folded scalars in `source`.

    A `>` block scalar folds each single line break in its content to a space,
    so refilling a run of its lines leaves the value the scalar parses to
    untouched. A line that does not fold that way ends the open run instead of
    joining it, each such line keeping a break or a space a refill would drop:

    - a blank line
    - a line indented past the scalar's own indent
    - a line ending in whitespace

    Whether a run holds prose worth filling is the caller's judgment, not this
    scan's.

    Returns:
        The 1-based line numbers of each run, in source order. A literal `|`
        scalar, whose breaks are content, and a file that is not YAML both
        yield an empty result.
    """
    if language_for(path) is not YAML:
        return ()
    return tuple(folded_runs(source))


def language_for(path: Path) -> Language | None:
    """Returns the language `path` holds by its suffix, or `None`."""
    return _BY_SUFFIX.get(path.suffix)
