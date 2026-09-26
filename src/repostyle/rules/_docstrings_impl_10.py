"""Internal docstring-rule implementation partition 10."""

from __future__ import annotations

import ast
import re
from typing import NamedTuple

from repostyle._shared import (
    _BULLET_PATTERN,
    _VERBATIM_LINE_PATTERN,
)
from repostyle.rules._docstrings_impl_11 import (
    InternalDocLine,
)


class InternalDocstringSegmenter:
    """Groups docstring lines into the prose units the rule grades.

    Feed lines in order with `consume`, call `close` after the last, then read
    `units`. The first paragraph is the summary; later margin paragraphs are
    body; a `Note:` section's body is treated as body; an `Args:`-style section
    yields one entry per item; a bullet item and its deeper-indented wrapped
    continuations form one bullet unit; and code, doctests, `Example:`
    sections, and verbatim lines yield nothing.
    """

    def __init__(self) -> None:
        self.units: list[InternalProseUnit] = []
        self._open: list[InternalDocLine] = []
        self._open_kind = "summary"
        self._in_fence = False
        self._section: str | None = None
        self._entry_indent: int | None = None
        self._bullet_indent: int | None = None
        self._summary_done = False

    def close(self) -> None:
        """Finishes the open unit, appending it to `units` if non-empty."""
        if not self._open:
            return
        if self._open_kind == "summary":
            self._summary_done = True
        last = self._open[-1]
        text = " ".join(line.text for line in self._open)
        linenos = tuple(line.lineno for line in self._open)
        self.units.append(
            InternalProseUnit(
                self._open_kind, last.lineno, last.column + 1, text, linenos
            )
        )
        self._open = []

    def consume(self, line: InternalDocLine) -> None:
        """Routes `line` to its unit, ending the open unit as needed."""
        if self._consume_structural(line):
            return
        if self._section == "code":
            return
        if _BULLET_PATTERN.match(line.text):
            self.close()
            self._open = [line]
            self._open_kind = "bullet"
            self._bullet_indent = line.relative_indent
            return
        if (
            self._open
            and self._open_kind == "bullet"
            and (self._bullet_indent is not None)
            and (line.relative_indent > self._bullet_indent)
        ):
            self._open.append(line)
            return
        if self._section == "entry":
            self._consume_entry(line)
        else:
            self._consume_paragraph(line)

    def _consume_entry(self, line: InternalDocLine) -> None:
        """Starts a new entry on a caption line, or extends the open one.

        An entry opens on a `name:`-style caption at the entry margin; a line
        that carries no caption continues the open entry, whether it wraps at a
        deeper indent or at the entry margin, so a `Returns:` description
        wrapped at one indent stays a single multi-line entry. An open bullet
        is closed first, so a flush follow-on line after a bullet item opens
        its own unit rather than silently joining the bullet -- only a
        deeper-indented line wraps an item.
        """
        if self._open and self._open_kind == "bullet":
            self.close()
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

    def _consume_paragraph(self, line: InternalDocLine) -> None:
        """Extends the open summary or body paragraph, or starts a new one."""
        if self._open and self._open_kind in ("summary", "body"):
            self._open.append(line)
            return
        self.close()
        self._open = [line]
        self._open_kind = "summary" if not self._summary_done else "body"

    def _consume_structural(self, line: InternalDocLine) -> bool:
        """Handles a blank, fence, doctest, header, or section-exit line.

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
        if line.relative_indent == 0 and text in InternalSECTION_HEADERS:
            self._enter_section(text)
            return True
        if self._section is not None and line.relative_indent == 0:
            self.close()
            self._section = None
            self._entry_indent = None
        return False

    def _enter_section(self, header: str) -> None:
        """Opens the section a header introduces, closing the open unit."""
        self.close()
        self._summary_done = True
        self._entry_indent = None
        if header in _ENTRY_SECTION_HEADERS:
            self._section = "entry"
        elif header in _CODE_SECTION_HEADERS:
            self._section = "code"
        else:
            self._section = "prose"


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

InternalSECTION_HEADERS = (
    _ENTRY_SECTION_HEADERS | _PROSE_SECTION_HEADERS | _CODE_SECTION_HEADERS
)

_SECTION_ENTRY_PATTERN = re.compile("^\\S+:(\\s|$)")


class InternalProseUnit(NamedTuple):
    kind: str
    "`summary`, `body`, `entry`, or `bullet`."
    lineno: int
    "Source line the unit's terminal punctuation sits on."
    col: int
    "1-based column the violation points at."
    text: str
    "The unit's lines joined into one string."
    linenos: tuple[int, ...]
    "The source lines the unit's prose occupies."


def internal_field_has_docstring(body: list[ast.stmt], index: int) -> bool:
    """Reports whether the statement after a field is a string docstring."""
    following = body[index + 1] if index + 1 < len(body) else None
    return (
        isinstance(following, ast.Expr)
        and isinstance(following.value, ast.Constant)
        and isinstance(following.value.value, str)
    )


def internal_has_dataclass_decorator(node: ast.ClassDef) -> bool:
    """Reports whether a class carries a dataclass decorator."""
    for decorator in node.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Name) and target.id == "dataclass":
            return True
        if isinstance(target, ast.Attribute) and target.attr == "dataclass":
            return True
    return False
