"""Docstring and markdown prose rules.

The placement rules move a summary that documents a unit into the
docstring slot ruff D401 grades, and reject docstring openings that
restate the identifier instead of stating the contract: no `Attributes:`
block, no double backticks, no leading summary comment, no field comment
standing in for a field docstring, and no filler opening.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

from pystyle.rules._shared import (
    _comment_text,
    _is_directive_comment,
    _is_prose_comment,
    _join_source_lines,
    _parse_python,
    _terminal_punctuation_fault,
)
from pystyle.rules._violation import (
    RS_FIELD_COMMENT_AS_DOCSTRING,
    RS_FILLER_DOCSTRING_OPENING,
    RS_NO_ATTRIBUTES_BLOCK,
    RS_NO_DOUBLE_BACKTICKS,
    RS_SUMMARY_COMMENT_AS_DOCSTRING,
    RS_TERMINAL_PUNCTUATION,
    Violation,
)

ATTRIBUTES_SECTION_PATTERN = re.compile(r"^\s*Attributes:\s*$", re.MULTILINE)
DOUBLE_BACKTICK_PATTERN = re.compile(r"(?<!`)``(?!`)")

# A docstring opening that names the unit's category or hedges instead
# of stating its contract. Matched case-insensitively against the
# summary's first non-blank line.
_FILLER_OPENING_PATTERN = re.compile(
    r"^(this (function|method|class|module)\b|helper (to|for)\b|used to\b"
    r"|simply\b|just\b)",
    re.IGNORECASE,
)

# Google section headers, grouped by how their bodies are graded. An
# entry section holds `name: description` items checked per entry; a
# prose section's body is graded as prose; a code section is exempt.
_ENTRY_SECTION_HEADERS = frozenset(
    {
        "Args:",
        "Arguments:",
        "Attributes:",
        "Raises:",
        "Returns:",
        "Return:",
        "Yields:",
        "Yield:",
    }
)
_PROSE_SECTION_HEADERS = frozenset({"Note:", "Notes:"})
_CODE_SECTION_HEADERS = frozenset({"Example:", "Examples:"})
_SECTION_HEADERS = (
    _ENTRY_SECTION_HEADERS | _PROSE_SECTION_HEADERS | _CODE_SECTION_HEADERS
)
_BULLET_PATTERN = re.compile(r"^[-*+] ")
# A section entry's caption: a non-space run then a colon (`name:`,
# `name (type):`, `ValueError:`), which opens a fresh entry. A line
# without one continues the entry it follows.
_SECTION_ENTRY_PATTERN = re.compile(r"^\S+:(\s|$)")
# A markdown table row or a line made only of rule characters opens
# verbatim content whose terminal character is not prose punctuation.
_VERBATIM_LINE_PATTERN = re.compile(r"^\||^[-+=][-+=|\s]*$")


def check_no_attributes_block(path: Path, source: str) -> Iterator[Violation]:
    """Docstrings must not use a Google `Attributes:` block."""
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in _walk_docstring_owners(tree):
        docstring = ast.get_docstring(node, clean=False)
        if docstring is None:
            continue
        if ATTRIBUTES_SECTION_PATTERN.search(docstring) is None:
            continue
        yield Violation(
            getattr(node, "lineno", 1),
            getattr(node, "col_offset", 0) + 1,
            RS_NO_ATTRIBUTES_BLOCK,
            "use per-field attribute docstrings, not a Google `Attributes:` block",
        )


def check_no_double_backticks_in_md(path: Path, source: str) -> Iterator[Violation]:
    """Markdown prose may not use double backticks."""
    if path.suffix != ".md":
        return
    yield from _check_double_backticks_in_lines(source)


def check_no_double_backticks_in_docstrings(
    path: Path, source: str
) -> Iterator[Violation]:
    """Python docstring prose may not use double backticks."""
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in _walk_docstring_owners(tree):
        docstring = ast.get_docstring(node, clean=False)
        if docstring is None:
            continue
        if DOUBLE_BACKTICK_PATTERN.search(docstring):
            yield Violation(
                getattr(node, "lineno", 1),
                getattr(node, "col_offset", 0) + 1,
                RS_NO_DOUBLE_BACKTICKS,
                "use single backticks, not double, in docstrings",
            )


def fix_double_backticks(
    path: Path, source: str, skip_lines: frozenset[int] = frozenset()
) -> str:
    """Rewrite double backticks to single in `source`, the RS005 fix.

    A markdown file's prose lines and a Python file's docstring lines
    are rewritten; a fenced markdown block and a docstring whose owner
    line is in `skip_lines` are left untouched. Return the source
    unchanged when nothing rewrites.
    """
    if path.suffix == ".md":
        return _fix_double_backticks_md(source)
    tree = _parse_python(path, source)
    if tree is None:
        return source
    source_lines = source.splitlines()
    changed = False
    for node in _walk_docstring_owners(tree):
        constant = _docstring_constant(node)
        if constant is None or getattr(node, "lineno", 1) in skip_lines:
            continue
        end = constant.end_lineno or constant.lineno
        for lineno in range(constant.lineno, end + 1):
            rewritten = DOUBLE_BACKTICK_PATTERN.sub("`", source_lines[lineno - 1])
            if rewritten != source_lines[lineno - 1]:
                source_lines[lineno - 1] = rewritten
                changed = True
    return _join_source_lines(source, source_lines) if changed else source


def _fix_double_backticks_md(source: str) -> str:
    """Rewrite double backticks to single in a markdown file's prose."""
    source_lines = source.splitlines()
    in_fence = False
    changed = False
    for index, line in enumerate(source_lines):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        rewritten = DOUBLE_BACKTICK_PATTERN.sub("`", line)
        if rewritten != line:
            source_lines[index] = rewritten
            changed = True
    return _join_source_lines(source, source_lines) if changed else source


def check_summary_comment_as_docstring(path: Path, source: str) -> Iterator[Violation]:
    """A leading summary comment should be a docstring.

    A module, class, or function with no docstring whose first body
    position is a standalone prose comment carries a summary that ruff
    D401's mood check cannot see; move it into the docstring slot.
    """
    tree = _parse_python(path, source)
    if not isinstance(tree, ast.Module):
        return
    comments, _ = _comment_lines(source)
    source_lines = source.splitlines()
    yield from _module_summary_comment(tree, comments)
    for node in _summary_comment_owners(tree):
        if ast.get_docstring(node, clean=False) is not None or not node.body:
            continue
        line = _leading_comment_line(node, comments, source_lines)
        if line is None:
            continue
        column, text = comments[line]
        if not _is_prose_comment(_comment_text(text)):
            continue
        yield Violation(
            line,
            column + 1,
            RS_SUMMARY_COMMENT_AS_DOCSTRING,
            "leading summary comment should be a docstring",
        )


def check_field_comment_as_docstring(path: Path, source: str) -> Iterator[Violation]:
    """A dataclass field comment should be a field docstring.

    A field documented with a trailing prose comment and no following
    string-literal field docstring should carry that text as the
    per-field docstring the house style prefers.
    """
    tree = _parse_python(path, source)
    if not isinstance(tree, ast.Module):
        return
    _, trailing = _comment_lines(source)
    for node in _dataclass_classes(tree):
        for index, stmt in enumerate(node.body):
            if not isinstance(stmt, ast.AnnAssign):
                continue
            comment = trailing.get(stmt.end_lineno or stmt.lineno)
            if comment is None or not _is_prose_comment(_comment_text(comment)):
                continue
            if _field_has_docstring(node.body, index):
                continue
            yield Violation(
                stmt.lineno,
                stmt.col_offset + 1,
                RS_FIELD_COMMENT_AS_DOCSTRING,
                "document a dataclass field with a string-literal docstring "
                "below it, not a trailing comment",
            )


def check_filler_docstring_opening(path: Path, source: str) -> Iterator[Violation]:
    """A docstring may not open with a filler phrase.

    An opening like `This function`, `Helper to`, `Used to`, `Simply`,
    or `Just` restates the identifier or hedges rather than stating the
    contract; the summary's first words should name what the unit does.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in _walk_docstring_owners(tree):
        docstring = ast.get_docstring(node, clean=True)
        if docstring is None:
            continue
        summary = next(
            (line.strip() for line in docstring.splitlines() if line.strip()), ""
        )
        if _FILLER_OPENING_PATTERN.match(summary):
            yield Violation(
                getattr(node, "lineno", 1),
                getattr(node, "col_offset", 0) + 1,
                RS_FILLER_DOCSTRING_OPENING,
                "docstring opening restates the identifier; state the contract instead",
            )


def check_docstring_terminal_punctuation(
    path: Path, source: str
) -> Iterator[Violation]:
    """Every docstring prose unit must end with terminal punctuation.

    A summary, a body paragraph, and an `Args:`, `Returns:`, `Raises:`,
    or `Yields:` entry each close with `.`, `!`, or `?`, as PEP 257
    prescribes for the summary and the house style extends to the rest.
    Code (doctests, `Example:` sections, fenced blocks), bullet items, a
    list-introducing colon, and a unit ending in a URL are exempt.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in _walk_docstring_owners(tree):
        constant = _docstring_constant(node)
        if constant is None:
            continue
        for unit in _docstring_prose_units(constant):
            if _terminal_punctuation_fault(unit.text, is_prose=True) is None:
                continue
            yield Violation(
                unit.lineno,
                unit.col,
                RS_TERMINAL_PUNCTUATION,
                _terminal_punctuation_message(unit.kind),
            )


def fix_docstring_terminal_punctuation(
    path: Path, source: str, skip_lines: frozenset[int] = frozenset()
) -> str:
    """Append a period to each unterminated docstring prose unit, the RS030 fix.

    A summary, body paragraph, or section entry that the rule flags as
    missing terminal punctuation gains a trailing `.` after its content,
    before the closing quote when the quote shares the line. A unit
    whose line is in `skip_lines` is left untouched. Return the source
    unchanged when nothing appends.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return source
    source_lines = source.splitlines()
    changed = False
    for node in _walk_docstring_owners(tree):
        constant = _docstring_constant(node)
        if constant is None:
            continue
        for unit in _docstring_prose_units(constant):
            if unit.lineno in skip_lines:
                continue
            if _terminal_punctuation_fault(unit.text, is_prose=True) != "missing":
                continue
            line = source_lines[unit.lineno - 1]
            index = _terminal_insert_index(line, unit.lineno, constant)
            source_lines[unit.lineno - 1] = f"{line[:index]}.{line[index:]}"
            changed = True
    return _join_source_lines(source, source_lines) if changed else source


def _check_double_backticks_in_lines(source: str) -> Iterator[Violation]:
    in_fence = False
    for lineno, line in enumerate(source.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = DOUBLE_BACKTICK_PATTERN.search(line)
        if match:
            yield Violation(
                lineno,
                match.start() + 1,
                RS_NO_DOUBLE_BACKTICKS,
                "use single backticks, not double, in prose",
            )


def _comment_lines(source: str) -> tuple[dict[int, tuple[int, str]], dict[int, str]]:
    """Split a source's comments into the standalone and trailing maps.

    The first map keys each whole-line comment's line to its column and
    text; the second keys each line whose comment trails code to that
    comment's text. A comment is standalone when nothing but whitespace
    precedes it on its line.
    """
    source_lines = source.splitlines()
    standalone: dict[int, tuple[int, str]] = {}
    trailing: dict[int, str] = {}
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type != tokenize.COMMENT:
                continue
            lineno, column = token.start
            if source_lines[lineno - 1][:column].strip():
                trailing[lineno] = token.string
            else:
                standalone[lineno] = (column, token.string)
    except tokenize.TokenError:
        pass
    return standalone, trailing


def _dataclass_classes(tree: ast.Module) -> Iterator[ast.ClassDef]:
    """Yield every `@dataclass`-decorated class in `tree`."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and _has_dataclass_decorator(node):
            yield node


def _docstring_constant(node: ast.AST) -> ast.Constant | None:
    """Return `node`'s docstring string-literal node, or `None`."""
    body = getattr(node, "body", None)
    if not body:
        return None
    first = body[0]
    if (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        return first.value
    return None


def _docstring_prose_units(constant: ast.Constant) -> list[_ProseUnit]:
    """Group a docstring's lines into summary, body, and entry units."""
    segmenter = _DocstringSegmenter()
    for line in _doc_lines(constant):
        segmenter.consume(line)
    segmenter.close()
    return segmenter.units


def _doc_lines(constant: ast.Constant) -> list[_DocLine]:
    """Split a docstring literal into structure-tagged source lines.

    The first line abuts the opening quote, so it anchors its column at
    the literal and the body margin is taken from the first following
    non-blank line, with every later line's indent measured relative to
    it. The source line is clamped to the literal's physical span, so a
    docstring carrying escaped newlines or built by implicit
    concatenation still points within itself rather than past it.
    """
    lines = constant.value.splitlines()
    last = constant.end_lineno or constant.lineno
    margin = next(
        (len(line) - len(line.lstrip()) for line in lines[1:] if line.strip()),
        0,
    )
    result: list[_DocLine] = []
    for index, line in enumerate(lines):
        lineno = min(constant.lineno + index, last)
        column = constant.col_offset if index == 0 else len(line) - len(line.lstrip())
        relative = 0 if index == 0 else max(0, column - margin)
        result.append(_DocLine(lineno, column, relative, line.strip()))
    return result


class _DocLine(NamedTuple):
    lineno: int
    """1-based source line of this docstring line."""
    column: int
    """0-based leading-whitespace width, the violation's column anchor."""
    relative_indent: int
    """Indent relative to the docstring's body margin, for structure."""
    text: str
    """The line stripped of leading and trailing whitespace."""


class _DocstringSegmenter:
    """Group docstring lines into the prose units the rule grades.

    Feed lines in order with `consume`, call `close` after the last,
    then read `units`. The first paragraph is the summary; later margin
    paragraphs are body; a `Note:` section's body is treated as body; an
    `Args:`-style section yields one entry per item; and code, doctests,
    `Example:` sections, bullets, and verbatim lines yield nothing.
    """

    def __init__(self) -> None:
        self.units: list[_ProseUnit] = []
        self._open: list[_DocLine] = []
        self._open_kind = "summary"
        self._in_fence = False
        self._section: str | None = None
        self._entry_indent: int | None = None
        self._summary_done = False

    def close(self) -> None:
        """Finish the open unit, appending it to `units` if non-empty."""
        if not self._open:
            return
        if self._open_kind == "summary":
            self._summary_done = True
        last = self._open[-1]
        text = " ".join(line.text for line in self._open)
        self.units.append(
            _ProseUnit(self._open_kind, last.lineno, last.column + 1, text)
        )
        self._open = []

    def consume(self, line: _DocLine) -> None:
        """Route `line` to its unit, ending the open unit as needed."""
        if self._consume_structural(line):
            return
        if self._section == "code":
            return
        if _BULLET_PATTERN.match(line.text):
            self.close()
            return
        if self._section == "entry":
            self._consume_entry(line)
        else:
            self._consume_paragraph(line)

    def _consume_entry(self, line: _DocLine) -> None:
        """Start a new entry on a caption line, or extend the open one.

        An entry opens on a `name:`-style caption at the entry margin; a
        line that carries no caption continues the open entry, whether
        it wraps at a deeper indent or at the entry margin, so a
        `Returns:` description wrapped at one indent stays a single
        multi-line entry.
        """
        if self._entry_indent is None:
            self._entry_indent = line.relative_indent
        starts_entry = (
            line.relative_indent <= self._entry_indent
            and _SECTION_ENTRY_PATTERN.match(line.text) is not None
        )
        if not self._open or starts_entry:
            self.close()
            self._open = [line]
            self._open_kind = "entry"
        else:
            self._open.append(line)

    def _consume_paragraph(self, line: _DocLine) -> None:
        """Extend the open summary or body paragraph, or start a new one."""
        if self._open and self._open_kind in ("summary", "body"):
            self._open.append(line)
            return
        self.close()
        self._open = [line]
        self._open_kind = "summary" if not self._summary_done else "body"

    def _consume_structural(self, line: _DocLine) -> bool:
        """Handle a blank, fence, doctest, header, or section-exit line.

        Return whether `line` was structural and yields no prose unit.
        """
        text = line.text
        if not text:
            self.close()
            return True
        if text.startswith("```"):
            self.close()
            self._in_fence = not self._in_fence
            return True
        if self._in_fence:
            return True
        if text.startswith((">>>", "... ")) or _VERBATIM_LINE_PATTERN.match(text):
            self.close()
            return True
        if line.relative_indent == 0 and text in _SECTION_HEADERS:
            self._enter_section(text)
            return True
        if self._section is not None and line.relative_indent == 0:
            self.close()
            self._section = None
            self._entry_indent = None
        return False

    def _enter_section(self, header: str) -> None:
        """Open the section a header introduces, closing the open unit."""
        self.close()
        self._summary_done = True
        self._entry_indent = None
        if header in _ENTRY_SECTION_HEADERS:
            self._section = "entry"
        elif header in _CODE_SECTION_HEADERS:
            self._section = "code"
        else:
            self._section = "prose"


class _ProseUnit(NamedTuple):
    kind: str
    """`summary`, `body`, or `entry`."""
    lineno: int
    """Source line the unit's terminal punctuation sits on."""
    col: int
    """1-based column the violation points at."""
    text: str
    """The unit's lines joined into one string."""


def _field_has_docstring(body: list[ast.stmt], index: int) -> bool:
    """Report whether the statement after a field is a string-literal docstring."""
    following = body[index + 1] if index + 1 < len(body) else None
    return (
        isinstance(following, ast.Expr)
        and isinstance(following.value, ast.Constant)
        and isinstance(following.value.value, str)
    )


def _has_dataclass_decorator(node: ast.ClassDef) -> bool:
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Name) and target.id == "dataclass":
            return True
        if isinstance(target, ast.Attribute) and target.attr == "dataclass":
            return True
    return False


def _leading_comment_line(
    node: ast.AsyncFunctionDef | ast.ClassDef | ast.FunctionDef,
    comments: dict[int, tuple[int, str]],
    source_lines: list[str],
) -> int | None:
    """Return the line of `node`'s first-body-position standalone comment.

    The comment sits directly above the first body statement, with only
    blank lines between, below the definition header. A comment deeper
    in the body, or one trailing the signature, is not returned, so only
    the leading summary position is in scope.
    """
    line = node.body[0].lineno - 1
    while line > node.lineno:
        if line in comments:
            return line
        if not source_lines[line - 1].strip():
            line -= 1
            continue
        return None
    return None


def _module_summary_comment(
    tree: ast.Module, comments: dict[int, tuple[int, str]]
) -> Iterator[Violation]:
    """Flag a module whose first prose line is a comment, not a docstring.

    A leading shebang, coding, or tool-directive line is skipped, so the
    summary comment beneath it is still reached; the first non-directive
    standalone comment then decides, since only the leading position is
    in scope.
    """
    if ast.get_docstring(tree, clean=False) is not None:
        return
    first_code = tree.body[0].lineno if tree.body else None
    for line in sorted(comments):
        if first_code is not None and line >= first_code:
            return
        text = _comment_text(comments[line][1])
        if _is_directive_comment(text):
            continue
        if _is_prose_comment(text):
            yield Violation(
                line,
                comments[line][0] + 1,
                RS_SUMMARY_COMMENT_AS_DOCSTRING,
                "leading summary comment should be a module docstring",
            )
        return


def _summary_comment_owners(
    tree: ast.Module,
) -> Iterator[ast.AsyncFunctionDef | ast.ClassDef | ast.FunctionDef]:
    """Yield every class and function definition in `tree`."""
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef | ast.ClassDef | ast.FunctionDef):
            yield node


def _terminal_insert_index(line: str, lineno: int, constant: ast.Constant) -> int:
    """Return the column on `line` just past a prose unit's last content.

    When the closing quote shares the unit's last line, the index lands
    before it; otherwise it lands after the line's last non-space
    character. The closing delimiter is found by matching the line's
    suffix rather than `end_col_offset`, which is a byte offset and so
    misplaces the mark on a line carrying non-ASCII text.
    """
    stripped = line.rstrip()
    if lineno == constant.end_lineno:
        for delimiter in ('"""', "'''", '"', "'"):
            if stripped.endswith(delimiter):
                return len(stripped[: -len(delimiter)].rstrip())
    return len(stripped)


def _terminal_punctuation_message(kind: str) -> str:
    """Return the fix message for a missing terminal mark on `kind`."""
    subject = {
        "summary": "docstring summary",
        "body": "docstring body paragraph",
        "entry": "section entry",
    }[kind]
    return f"{subject} should end with terminal punctuation (`.`, `!`, or `?`)"


def _walk_docstring_owners(
    tree: ast.AST,
) -> Iterator[ast.AsyncFunctionDef | ast.ClassDef | ast.FunctionDef | ast.Module]:
    for node in ast.walk(tree):
        if isinstance(
            node, ast.AsyncFunctionDef | ast.ClassDef | ast.FunctionDef | ast.Module
        ):
            yield node
