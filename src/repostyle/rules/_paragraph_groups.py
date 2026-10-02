"""Groups adjacent documentation lines into paragraphs."""

from __future__ import annotations

from repostyle._shared import (
    _LIST_ITEM_PATTERN,
    _VERBATIM_LINE_PATTERN,
)
from repostyle.rules._display_width import (
    InternalFillLine,
    InternalLABEL_LINE_PATTERN,
    InternalSECTION_ENTRY_PATTERN,
)
from repostyle.rules._reflow import (
    InternalPREFORMATTED_LINE_PATTERN,
    InternalSECTION_HEADERS,
)


class InternalParagraphGrouper:
    """Groups docstring or comment lines into fillable paragraph units.

    Feed lines in order with `consume`, call `close` after the last line, then
    read the gathered paragraphs from `units`. A verbatim or blank line closes
    the open unit without joining it; a marker line starts a fresh hanging
    paragraph; a plain line either continues the open unit at its established
    indent or starts its own.
    """

    def __init__(self) -> None:
        self.units: list[list[InternalFillLine]] = []
        self._unit: list[InternalFillLine] = []
        self._first_indent = 0
        self._cont_indent: int | None = None
        self._in_fence = False
        self._section_indent: int | None = None
        self._entry_indent: int | None = None

    def close(self) -> None:
        """Finishes the open unit, appending it to `units` if non-empty."""
        if self._unit:
            self.units.append(self._unit)
        self._unit = []
        self._cont_indent = None

    def consume(self, line: InternalFillLine) -> None:
        """Routes `line` to its handler, ending the open unit as needed."""
        if self._consume_verbatim(line):
            return
        self._exit_finished_section(line)
        if self._consume_marker(line):
            return
        self._consume_paragraph(line)

    def _consume_marker(self, line: InternalFillLine) -> bool:
        """Opens a fresh unit for a header, entry, bullet, or label line.

        A section header opens a new section and is not itself filled. A
        section entry, bullet, or label line starts a hanging paragraph.
        Returns whether `line` was a marker and has been handled.
        """
        if line.text in InternalSECTION_HEADERS:
            self.close()
            self._section_indent = line.indent
            self._entry_indent = None
            return True
        if (
            self._starts_entry(line)
            or _LIST_ITEM_PATTERN.match(line.text)
            or InternalLABEL_LINE_PATTERN.match(line.text)
        ):
            self.close()
            self._unit = [line]
            self._first_indent = line.indent
            return True
        return False

    def _consume_paragraph(self, line: InternalFillLine) -> None:
        """Appends `line` to the open unit or starts a unit with it.

        A line indented past a one-line unit sets that unit's continuation
        indent; otherwise a line matching the established indent continues the
        unit. Any other line opens its own unit.
        """
        if self._unit and self._extend_open_unit(line):
            return
        self._unit = [line]
        self._first_indent = line.indent

    def _consume_verbatim(self, line: InternalFillLine) -> bool:
        """Closes the unit and reports whether `line` is unfillable.

        Blank lines, code fences, doctests, table or rule lines, and
        preformatted lines are verbatim: they never join a paragraph. A fence
        line also toggles whether subsequent lines sit inside a fenced block.
        """
        if not line.text:
            self.close()
            return True
        if line.text.startswith("```"):
            self.close()
            self._in_fence = not self._in_fence
            return True
        if self._in_fence or line.text.startswith((">>>", "... ")):
            self.close()
            return True
        if _VERBATIM_LINE_PATTERN.match(
            line.text
        ) or InternalPREFORMATTED_LINE_PATTERN.search(line.text):
            self.close()
            return True
        return False

    def _exit_finished_section(self, line: InternalFillLine) -> None:
        """Clears section tracking when `line` falls back to its margin."""
        if self._section_indent is not None and line.indent <= self._section_indent:
            self._section_indent = None
            self._entry_indent = None

    def _extend_open_unit(self, line: InternalFillLine) -> bool:
        """Appends `line` to the open unit when its indent fits, else ends it.

        Returns whether `line` joined the open unit.
        """
        if len(self._unit) == 1 and line.indent > self._first_indent:
            self._cont_indent = line.indent
            self._unit.append(line)
            return True
        expected = (
            self._first_indent if self._cont_indent is None else self._cont_indent
        )
        if line.indent == expected:
            self._unit.append(line)
            return True
        self.close()
        return False

    def _starts_entry(self, line: InternalFillLine) -> bool:
        """Reports whether `line` begins an entry within the open section.

        Latches the section's entry indent to the first line examined, so later
        lines count as entries only when they align with it.
        """
        if self._section_indent is None:
            return False
        if self._entry_indent is None:
            self._entry_indent = line.indent
        return (
            line.indent == self._entry_indent
            and InternalSECTION_ENTRY_PATTERN.match(line.text) is not None
        )
