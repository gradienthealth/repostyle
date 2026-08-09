"""The cross-language `#`-comment extractor shared by the comment rules.

RS009 (paragraph wrapping), RS022 (tag format), RS030 (terminal punctuation),
and the suppression parser each read `#` comments from Python, TOML, YAML, and
shell. This module holds the one extractor they share: Python through the
tokenizer; TOML, YAML, and shell through a string- and block-aware line scan.
"""

from __future__ import annotations

import io
import re
import tokenize
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

# A YAML block scalar introducer: a value that, after a `:` or `-` lead or
# standing at the line start, is a `|` or `>` carrying only chomping and indent
# indicators, so the indented lines that follow are literal.
_BLOCK_SCALAR_PATTERN = re.compile(r"(?:[:-]\s+|^\s*)[|>][0-9+-]*\s*$")

# The file types whose `#` comments the comment rules read. Python is
# tokenized; TOML, YAML, and shell are scanned line by line. A type absent here
# is never comment-checked.
COMMENT_SUFFIXES = frozenset({".py", ".toml", ".yaml", ".yml", ".sh"})


class _CommentToken(NamedTuple):
    lineno: int
    """1-based line the comment starts on."""
    column: int
    """0-based column of the leading hash."""
    string: str
    """The comment from its leading hash to the end of the line."""
    is_trailing: bool
    """Whether code or data precedes the comment on its line."""


# Cache on (path, source) so a file is scanned once and the result shared
# across the rules that read it -- RS009, RS022, RS030, and the suppression
# parser -- the way `_parse_python` caches the AST. A tuple is returned so the
# cached value is safe to iterate repeatedly.
@lru_cache(maxsize=128)
def extract_comments(path: Path, source: str) -> tuple[_CommentToken, ...]:
    """Returns each `#` comment in `source`, dispatched by file type.

    A Python file is tokenized. A TOML, YAML, or shell file is scanned line by
    line under that language's string and block rules, so a `#` inside a
    string, a TOML multi-line string, a YAML block scalar, or a shell heredoc
    is not mistaken for a comment. A file of any other type yields nothing. The
    scan is conservative: an unrecognised construct keeps its `#` out of the
    results rather than risk flagging string content.
    """
    suffix = path.suffix
    if suffix == ".py":
        return tuple(_python_comments(source))
    if suffix == ".toml":
        return tuple(_toml_comments(source))
    if suffix in {".yaml", ".yml"}:
        return tuple(_yaml_comments(source))
    if suffix == ".sh":
        return tuple(_shell_comments(source))
    return ()


def _python_comments(source: str) -> Iterator[_CommentToken]:
    """Yields each comment token in Python `source` via the tokenizer.

    Tokens are yielded as the tokenizer produces them, so a fault in the tail
    still surfaces the comments before it.
    """
    source_lines = source.splitlines()
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type != tokenize.COMMENT:
                continue
            lineno, column = token.start
            is_trailing = bool(source_lines[lineno - 1][:column].strip())
            yield _CommentToken(lineno, column, token.string, is_trailing)
    except (tokenize.TokenError, SyntaxError):
        # An unterminated tail raises TokenError; inconsistent indentation
        # raises IndentationError/TabError (SyntaxError subclasses). Stop at
        # the fault and keep the comments already surfaced.
        return


def _toml_comments(source: str) -> Iterator[_CommentToken]:
    """Yields each `#` comment in TOML `source`, line by line.

    A multi-line string spanning lines carries its closing delimiter forward in
    `open_delimiter`, so a `#` inside it is never a comment.
    """
    open_delimiter: str | None = None
    for lineno, line in enumerate(source.splitlines(), start=1):
        column, open_delimiter = _toml_scan_line(line, open_delimiter)
        if column is not None:
            yield _token(lineno, line, column)


def _toml_scan_line(
    line: str, open_delimiter: str | None
) -> tuple[int | None, str | None]:
    """Finds a `#` comment in one TOML line, tracking multi-line strings.

    `open_delimiter`, when set, is the triple-quote delimiter closing an open
    multi-line string; the scan resumes after it closes on this line. Returns
    the comment column (or `None`) and the delimiter still open at the line's
    end (or `None`).
    """
    index = 0
    if open_delimiter is not None:
        close = line.find(open_delimiter)
        if close == -1:
            return None, open_delimiter
        index = close + len(open_delimiter)
    while index < len(line):
        char = line[index]
        if char == "#":
            return index, None
        if char in "\"'":
            triple = line[index : index + 3]
            if triple in ('"""', "'''"):
                close = line.find(triple, index + 3)
                if close == -1:
                    return None, triple
                index = close + 3
                continue
            index = _skip_toml_string(line, index)
            continue
        index += 1
    return None, None


def _skip_toml_string(line: str, index: int) -> int:
    """Returns the index past the single-line string opening at `index`.

    A basic (`"`) string honours backslash escapes; a literal (`'`) string does
    not. An unterminated string consumes the rest of the line, so its content
    is never read as a comment.
    """
    quote = line[index]
    index += 1
    while index < len(line):
        if quote == '"' and line[index] == "\\":
            index += 2
            continue
        if line[index] == quote:
            return index + 1
        index += 1
    return len(line)


def _yaml_comments(source: str) -> Iterator[_CommentToken]:
    """Yields each `#` comment in YAML `source`, line by line.

    A `|` or `>` block scalar records its introducer indent in `block_indent`;
    the deeper-indented lines that follow are literal, so a `#` among them is
    never read as a comment.
    """
    block_indent: int | None = None
    for lineno, line in enumerate(source.splitlines(), start=1):
        if block_indent is not None and _inside_block(line, block_indent):
            continue
        block_indent = None
        column = _yaml_comment_column(line)
        content = line if column is None else line[:column]
        if _opens_block_scalar(content):
            block_indent = _indent_of(line)
        if column is not None:
            yield _token(lineno, line, column)


def _inside_block(line: str, block_indent: int) -> bool:
    """Reports whether `line` sits in a block scalar at `block_indent`."""
    return not line.strip() or _indent_of(line) > block_indent


def _indent_of(line: str) -> int:
    """Returns the count of leading spaces on `line`."""
    return len(line) - len(line.lstrip(" "))


def _opens_block_scalar(content: str) -> bool:
    """Reports whether `content` is a YAML line opening a block scalar."""
    return _BLOCK_SCALAR_PATTERN.search(content) is not None


def _yaml_comment_column(line: str) -> int | None:
    """Returns the column of a `#` comment in one YAML line, or `None`.

    A `#` opens a comment only at the line start or after whitespace, and never
    inside a quoted scalar. A double-quoted scalar honours backslash escapes; a
    single-quoted one escapes a quote by doubling it.
    """
    index = 0
    while index < len(line):
        char = line[index]
        if char == "#" and (index == 0 or line[index - 1] in " \t"):
            return index
        if char == '"':
            index = _skip_yaml_double(line, index)
            continue
        if char == "'":
            index = _skip_yaml_single(line, index)
            continue
        index += 1
    return None


def _skip_yaml_double(line: str, index: int) -> int:
    """Returns the index past the double-quoted scalar opening at `index`."""
    index += 1
    while index < len(line):
        if line[index] == "\\":
            index += 2
            continue
        if line[index] == '"':
            return index + 1
        index += 1
    return len(line)


def _skip_yaml_single(line: str, index: int) -> int:
    """Returns the index past the single-quoted scalar opening at `index`."""
    index += 1
    while index < len(line):
        if line[index] == "'":
            if line[index + 1 : index + 2] == "'":
                index += 2
                continue
            return index + 1
        index += 1
    return len(line)


# A bare heredoc delimiter word, optionally backslash-quoted (`<<\EOF`). A
# leading letter or underscore keeps a `<< 2` arithmetic shift from reading as
# a redirection, since a delimiter starting with a digit is not used in
# practice.
_HEREDOC_WORD_PATTERN = re.compile(r"\\?[A-Za-z_][A-Za-z0-9_]*")


def _shell_comments(source: str) -> Iterator[_CommentToken]:
    """Yields each `#` comment in shell `source`, line by line.

    A `#` opens a comment only at the line start or after whitespace, so a
    `${var#pat}` expansion, a `$#`, and a `#` glued inside a word stay code. A
    quoted string, an ANSI-C `$'...'` string, and an arithmetic `$(( ))`
    expansion are skipped, so a `#` inside them is never a comment; a string or
    heredoc body spanning lines carries forward in `_ShellState`. A `#!`
    shebang is yielded like any comment.
    """
    state = _ShellState(None, None)
    for lineno, line in enumerate(source.splitlines(), start=1):
        column, state = _shell_scan_line(line, state)
        if column is not None:
            yield _token(lineno, line, column)


def _shell_scan_line(line: str, state: _ShellState) -> tuple[int | None, _ShellState]:
    """Finds a `#` comment in one shell line, resuming any cross-line state.

    A string open from a prior line is closed first, then the rest of the line
    scans as code; a line inside a heredoc body yields no comment until the
    terminator line closes it. Returns the comment column (or `None`) and the
    state still open at the line's end.
    """
    if state.open_quote is not None:
        end = _shell_string_end(line, 0, state.open_quote)
        if end is None:
            return None, state
        return _shell_scan_code(line, end)
    if state.heredoc is not None:
        if _heredoc_terminated(line, state.heredoc):
            return None, _ShellState(None, None)
        return None, state
    return _shell_scan_code(line, 0)


def _shell_scan_code(line: str, start: int) -> tuple[int | None, _ShellState]:
    """Scans `line` from `start` for a `#` comment, outside any open string.

    Skips a backslash-escaped character, an ANSI-C `$'...'` string, an
    arithmetic `$(( ))` expansion, a `<<<` here-string, and a quoted string, so
    neither a `#` inside one nor a here-string's own `<<<` is misread. A
    heredoc redirection is recorded but the scan continues, so a trailing
    comment on the redirection line is still found. Returns the `#` column (or
    `None`) and the state open at the line's end.
    """
    index = start
    pending: _Heredoc | None = None
    while index < len(line):
        if line[index] == "#" and _opens_comment(line, index):
            return index, _ShellState(None, pending)
        step = _shell_skip(line, index)
        if step is not None:
            index = step
            continue
        opener = _heredoc_opener(line, index)
        if opener is not None:
            heredoc, index = opener
            pending = pending or heredoc
            continue
        if line[index] in "\"'":
            end = _shell_string_end(line, index + 1, line[index])
            if end is None:
                return None, _ShellState(line[index], pending)
            index = end
            continue
        index += 1
    return None, _ShellState(None, pending)


def _heredoc_opener(line: str, index: int) -> tuple[_Heredoc, int] | None:
    """Parses a `<<WORD` heredoc redirection at `index`, or returns `None`.

    Handles `<<`, the tab-stripping `<<-`, and a quoted (`<<'EOF'`) or bare
    delimiter. Returns the heredoc and the index past the delimiter, so the
    rest of the line still scans for a trailing comment.
    """
    if not line.startswith("<<", index):
        return None
    cursor = index + 2
    has_tab_stripping = line[cursor : cursor + 1] == "-"
    if has_tab_stripping:
        cursor += 1
    while cursor < len(line) and line[cursor] in " \t":
        cursor += 1
    terminator, cursor = _heredoc_delimiter(line, cursor)
    if terminator is None:
        return None
    return _Heredoc(terminator, has_tab_stripping), cursor


def _heredoc_delimiter(line: str, index: int) -> tuple[str | None, int]:
    """Reads a heredoc delimiter word at `index`, quoted or bare.

    Returns the unquoted terminator and the index past it, or `(None, index)`
    when no delimiter word follows, so the `<<` reads as a shift operator
    rather than a redirection.
    """
    if index < len(line) and line[index] in "\"'":
        quote = line[index]
        close = line.find(quote, index + 1)
        if close == -1:
            return None, index
        return line[index + 1 : close], close + 1
    match = _HEREDOC_WORD_PATTERN.match(line, index)
    if match is None:
        return None, index
    return match.group().lstrip("\\"), match.end()


def _heredoc_terminated(line: str, heredoc: _Heredoc) -> bool:
    """Reports whether `line` is the delimiter ending a heredoc body.

    A `<<-` heredoc lets the delimiter line carry leading tabs, so those are
    stripped before the comparison; otherwise the line must equal the delimiter
    exactly.
    """
    candidate = line.lstrip("\t") if heredoc.has_tab_stripping else line
    return candidate == heredoc.terminator


def _opens_comment(line: str, index: int) -> bool:
    """Reports whether the `#` at `index` begins a shell comment.

    A `#` begins a comment only at the line start or after whitespace, so a `#`
    glued to a word (`$#`, `${v#p}`, `a#b`) stays code.
    """
    return index == 0 or line[index - 1] in " \t"


def _shell_skip(line: str, index: int) -> int | None:
    r"""Returns the index past a construct skipped whole, or `None`.

    A backslash escapes the next character, including a line-continuation `\`
    at the line's end; `$'...'` is an ANSI-C string honouring backslash
    escapes; `$(( ))` is an arithmetic expansion whose `#` base marker and `<<`
    shift must not read as a comment or a heredoc; `<<<` is a here-string
    operator, whose three characters skip together so the trailing `<<` cannot
    open a spurious heredoc.
    """
    if line[index] == "\\":
        return index + 2
    if line.startswith("$'", index):
        return _shell_ansi_c_end(line, index + 2)
    if line.startswith("$((", index):
        return _shell_arithmetic_end(line, index + 3)
    if line.startswith("<<<", index):
        return index + 3
    return None


def _shell_ansi_c_end(line: str, index: int) -> int:
    r"""Returns the index past an ANSI-C `$'...'` string opened before `index`.

    A backslash escapes the next character, so `\'` does not close the string.
    An unterminated string consumes the rest of the line.
    """
    while index < len(line):
        if line[index] == "\\":
            index += 2
            continue
        if line[index] == "'":
            return index + 1
        index += 1
    return len(line)


def _shell_arithmetic_end(line: str, index: int) -> int:
    """Returns the index past a `$(( ))` expansion opened before `index`.

    Tracks parenthesis depth so a nested `(` pairs before the closing `))`. An
    unterminated expansion consumes the rest of the line.
    """
    depth = 2
    while index < len(line):
        if line[index] == "(":
            depth += 1
        elif line[index] == ")":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return len(line)


def _shell_string_end(line: str, index: int, quote: str) -> int | None:
    """Returns the index past a `quote`-delimited string, or `None` if open.

    A double-quoted string honours backslash escapes; a single-quoted one is
    literal. `None` means the string runs past the line's end, so the caller
    carries it to the next line.
    """
    while index < len(line):
        if quote == '"' and line[index] == "\\":
            index += 2
            continue
        if line[index] == quote:
            return index + 1
        index += 1
    return None


def _token(lineno: int, line: str, column: int) -> _CommentToken:
    """Builds a comment token for the `#` at `column` on `line`."""
    return _CommentToken(lineno, column, line[column:], bool(line[:column].strip()))


class _Heredoc(NamedTuple):
    terminator: str
    """The word whose own line ends the heredoc body."""
    has_tab_stripping: bool
    """Whether a `<<-` heredoc lets the terminator line carry leading tabs."""


class _ShellState(NamedTuple):
    open_quote: str | None
    """A `'` or `"` opened on a prior line and still unclosed, else `None`."""
    heredoc: _Heredoc | None
    """An open heredoc whose body suppresses comments, else `None`."""
