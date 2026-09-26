"""String-aware shell comment extraction."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import NamedTuple

from repostyle._comment_types import _CommentToken

# A bare heredoc delimiter word, optionally backslash-quoted (`<<\EOF`). A
# leading letter or underscore keeps a `<< 2` arithmetic shift from reading as
# a redirection, since a delimiter starting with a digit is not used in
# practice.
_HEREDOC_WORD_PATTERN = re.compile(r"\\?[A-Za-z_][A-Za-z0-9_]*")

# The shell contexts the scan nests, innermost last in `_ShellState.contexts`.
# A substitution marker also stands for a `(` group opened inside one, so the
# group's `)` does not close the substitution early.
_DOUBLE_QUOTED = '"'
_SINGLE_QUOTED = "'"
_SUBSTITUTION = "("
_BACKTICK = "`"


def shell_comments(source: str) -> Iterator[_CommentToken]:
    """Yields each `#` comment in shell `source`, line by line.

    A `#` opens a comment only at the line start or after whitespace, so a
    `${var#pat}` expansion, a `$#`, and a `#` glued inside a word stay code. A
    quoted string, an ANSI-C `$'...'` string, and an arithmetic `$(( ))`
    expansion are skipped, so a `#` inside them is never a comment; the open
    contexts and any heredoc body carry forward in `_ShellState`. A `#!`
    shebang is yielded like any comment.
    """
    state = _ShellState((), None)
    for lineno, line in enumerate(source.splitlines(), start=1):
        column, state = _shell_scan_line(line, state)
        if column is not None:
            yield _token(lineno, line, column)


def _shell_scan_line(line: str, state: _ShellState) -> tuple[int | None, _ShellState]:
    """Finds a `#` comment in one shell line, resuming any cross-line state.

    Contexts open from a prior line resume where they left off; a line inside a
    heredoc body yields no comment until the terminator line closes it. Returns
    the comment column (or `None`) and the state still open at the line's end.
    """
    if state.contexts:
        return _shell_scan(line, state.contexts)
    if state.heredoc is not None:
        if _heredoc_terminated(line, state.heredoc):
            return None, _ShellState((), None)
        return None, state
    return _shell_scan(line, ())


def _shell_scan(line: str, contexts: tuple[str, ...]) -> tuple[int | None, _ShellState]:
    """Scans `line` for a `#` comment under the contexts open around it.

    Quoting nests, so which characters matter depends on the innermost open
    context rather than on the line alone: `$(...)` and a backtick substitution
    start a fresh code context inside a double-quoted string, and a quote of
    the other style inside any string is literal. Tracking that is what keeps a
    `sed 's/"/X/'` inside `"$( )"` from closing the outer string and stranding
    every later `#` inside a phantom one.

    Outside a string, a backslash-escaped character, an ANSI-C `$'...'` string,
    an arithmetic `$(( ))` expansion, and a `<<<` here-string are skipped
    whole, so neither a `#` inside one nor a here-string's own `<<` is misread.
    A heredoc redirection is recorded but the scan continues, so a trailing
    comment on the redirection line is still found.

    Returns:
        The `#` column (or `None`) and the state open at the line's end.
    """
    stack = list(contexts)
    pending: _Heredoc | None = None
    index = 0
    while index < len(line):
        innermost = stack[-1] if stack else None
        if innermost == _SINGLE_QUOTED:
            index = _scan_single_quoted(line, index, stack)
            continue
        if innermost == _DOUBLE_QUOTED:
            index = _scan_double_quoted(line, index, stack)
            continue
        if line[index] == "#" and _opens_comment(line, index):
            return index, _ShellState(tuple(stack), pending)
        step = _shell_skip(line, index)
        if step is not None:
            index = step
            continue
        opener = _heredoc_opener(line, index)
        if opener is not None:
            heredoc, index = opener
            pending = pending or heredoc
            continue
        index = _scan_code(line, index, stack)
    return None, _ShellState(tuple(stack), pending)


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


def _scan_code(line: str, index: int, stack: list[str]) -> int:
    """Advances one character through a code context, updating `stack`.

    A quote opens the string it delimits. A backtick opens a substitution, or
    closes the one it already opened. A `$(` opens a command substitution, and
    a `(` nested inside one is pushed too so its `)` does not close the
    substitution early. A `(` at the top level is ignored, since a `case`
    pattern and a function header carry unpaired parentheses.
    """
    char = line[index]
    innermost = stack[-1] if stack else None
    if char == _BACKTICK:
        if innermost == _BACKTICK:
            stack.pop()
        else:
            stack.append(_BACKTICK)
        return index + 1
    if line.startswith("$(", index):
        stack.append(_SUBSTITUTION)
        return index + 2
    if char in (_DOUBLE_QUOTED, _SINGLE_QUOTED):
        stack.append(char)
        return index + 1
    if char == "(" and _SUBSTITUTION in stack:
        stack.append(_SUBSTITUTION)
    elif char == ")" and innermost == _SUBSTITUTION:
        stack.pop()
    return index + 1


def _scan_double_quoted(line: str, index: int, stack: list[str]) -> int:
    r"""Advances one character through a double-quoted string.

    A backslash escapes the next character, so `\"` does not end the string,
    and a `'` inside is literal. A `$(` or a backtick opens a nested code
    context where quoting starts afresh, so a quote inside it belongs to that
    context rather than closing this string. `stack` is pushed or popped
    accordingly.
    """
    char = line[index]
    if char == "\\":
        return index + 2
    if char == _DOUBLE_QUOTED:
        stack.pop()
        return index + 1
    if line.startswith("$(", index):
        stack.append(_SUBSTITUTION)
        return index + 2
    if char == _BACKTICK:
        stack.append(_BACKTICK)
        return index + 1
    return index + 1


def _scan_single_quoted(line: str, index: int, stack: list[str]) -> int:
    r"""Advances one character through a single-quoted string.

    A single-quoted string has no escapes at all, so a backslash is literal
    there and only a `'` ends it, popping `stack`. That is why `'it'\''s'` is
    three adjacent strings rather than one holding an escaped quote, and why a
    `"` inside is just a character.
    """
    if line[index] == _SINGLE_QUOTED:
        stack.pop()
    return index + 1


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


def _token(lineno: int, line: str, column: int) -> _CommentToken:
    """Builds a comment token for the `#` at `column` on `line`."""
    return _CommentToken(lineno, column, line[column:], bool(line[:column].strip()))


class _Heredoc(NamedTuple):
    terminator: str
    """The word whose own line ends the heredoc body."""
    has_tab_stripping: bool
    """Whether a `<<-` heredoc lets the terminator line carry leading tabs."""


class _ShellState(NamedTuple):
    contexts: tuple[str, ...]
    """Strings and substitutions open at a line's end, innermost last."""
    heredoc: _Heredoc | None
    """An open heredoc whose body suppresses comments, else `None`."""
