"""Docstring and markdown prose rules.

The placement rules move a summary that documents a unit into the docstring
slot this package's own doc-content rules can see, and reject docstring
openings that restate the identifier instead of stating the contract: no
`Attributes:` block, no double backticks, no leading summary comment, no field
comment standing in for a field docstring, no filler opening, and no
imperative-mood opening verb.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

from repostyle.rules._shared import (
    _comment_text,
    _is_directive_comment,
    _is_prose_comment,
    _join_source_lines,
    _parse_python,
    _repostyle_table,
    _string_list,
    _terminal_punctuation_fault,
    find_pyproject,
)
from repostyle.rules._violation import (
    RS_FIELD_COMMENT_AS_DOCSTRING,
    RS_FILLER_DOCSTRING_OPENING,
    RS_IMPERATIVE_DOCSTRING_OPENING,
    RS_NO_ATTRIBUTES_BLOCK,
    RS_NO_DOUBLE_BACKTICKS,
    RS_SUMMARY_COMMENT_AS_DOCSTRING,
    RS_TERMINAL_PUNCTUATION,
    RS_UNBACKTICKED_CODE_REFERENCE,
    Violation,
)
from repostyle.rules.imperative_verbs import (
    _IMPERATIVE_OPENING_PATTERN,
    _IMPERATIVE_VERBS,
    IMPERATIVE_VERB_CONJUGATIONS,
    _conjugate,
)

ATTRIBUTES_SECTION_PATTERN = re.compile(r"^\s*Attributes:\s*$", re.MULTILINE)
DOUBLE_BACKTICK_PATTERN = re.compile(r"(?<!`)``(?!`)")

# A docstring opening that names the unit's category or hedges instead of
# stating its contract. Matched case-insensitively against the summary's first
# non-blank line.
_FILLER_OPENING_PATTERN = re.compile(
    r"^(this (function|method|class|module)\b|helper (to|for)\b|used to\b"
    r"|simply\b|just\b)",
    re.IGNORECASE,
)

# Google section headers, grouped by how their bodies are graded. An entry
# section holds `name: description` items checked per entry; a prose section's
# body is graded as prose; a code section is exempt.
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
# `name (type):`, `ValueError:`), which opens a fresh entry. A line without one
# continues the entry it follows.
_SECTION_ENTRY_PATTERN = re.compile(r"^\S+:(\s|$)")
# A markdown table row or a line made only of rule characters opens verbatim
# content whose terminal character is not prose punctuation.
_VERBATIM_LINE_PATTERN = re.compile(r"^\||^[-+=][-+=|\s]*$")

# The Python literal constants read as code in prose just as a name does, so
# RS036 treats them as always-known references beside the module's own names.
_LITERAL_CONSTANTS = frozenset({"None", "True", "False"})
# A backtick-delimited span or a URL, both dropped before RS036 scans a unit: a
# name already in code font, or one sitting inside a link, is not a bare prose
# reference.
_BACKTICK_SPAN_PATTERN = re.compile(r"`[^`]*`")
_URL_PATTERN = re.compile(r"https?://\S+")
# A Python identifier, the token RS036 tests against the known-name set
_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# An entry unit leads with its own `name:` or `name (type):` caption, which
# documents the name rather than referencing it, so RS036 strips the caption
# before scanning.
_ENTRY_CAPTION_PATTERN = re.compile(r"^\S+(?:\s*\([^)]*\))?:\s*")
_SENTENCE_ENDINGS = (".", "!", "?")


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
    """Rewrites double backticks to single in `source`, the RS005 fix.

    A markdown file's prose lines and a Python file's docstring lines are
    rewritten; a fenced markdown block and a docstring whose owner line is in
    `skip_lines` are left untouched.

    Returns:
        The source with double backticks rewritten to single, unchanged when
        nothing rewrites.
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
    """Rewrites double backticks to single in a markdown file's prose."""
    source_lines = source.splitlines()
    changed = False
    for index, line in _unfenced_md_lines(source):
        rewritten = DOUBLE_BACKTICK_PATTERN.sub("`", line)
        if rewritten != line:
            source_lines[index] = rewritten
            changed = True
    return _join_source_lines(source, source_lines) if changed else source


def check_summary_comment_as_docstring(path: Path, source: str) -> Iterator[Violation]:
    """A leading summary comment should be a docstring.

    A module, class, or function with no docstring whose first body position is
    a standalone prose comment carries a summary that this package's own
    docstring-content rules cannot see; move it into the docstring slot.
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
    string-literal field docstring should carry that text as the per-field
    docstring the house style prefers.
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

    An opening like `This function`, `Helper to`, `Used to`, `Simply`, or
    `Just` restates the identifier or hedges rather than stating the contract;
    the summary's first words should name what the unit does.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in _walk_docstring_owners(tree):
        docstring = ast.get_docstring(node, clean=True)
        if docstring is None:
            continue
        summary = _docstring_summary_line(docstring)
        if _FILLER_OPENING_PATTERN.match(summary):
            yield Violation(
                getattr(node, "lineno", 1),
                getattr(node, "col_offset", 0) + 1,
                RS_FILLER_DOCSTRING_OPENING,
                "docstring opening restates the identifier; state the contract instead",
            )


def check_imperative_docstring_opening(path: Path, source: str) -> Iterator[Violation]:
    """A docstring summary must open in descriptive, not imperative, mood.

    The house convention states a unit's own contract descriptively, in the
    third person (`Returns the lease.`), not as a command (`Return the
    lease.`), matching Google's own style guide rather than PEP 257's
    imperative recommendation. A summary whose first word is a known
    bare-infinitive verb should conjugate it to third-person singular. A repo
    tunes the verb set for its own domain via `imperative-verbs-extra` and
    `imperative-verbs-exclude` in `[tool.repostyle]`.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    pyproject = find_pyproject(path)
    conjugations = _effective_conjugations(pyproject)
    pattern = _effective_pattern(pyproject)
    for node in _walk_docstring_owners(tree):
        docstring = ast.get_docstring(node, clean=True)
        if docstring is None:
            continue
        summary = _docstring_summary_line(docstring)
        match = pattern.match(summary)
        if match is None:
            continue
        verb = match.group(1)
        yield Violation(
            getattr(node, "lineno", 1),
            getattr(node, "col_offset", 0) + 1,
            RS_IMPERATIVE_DOCSTRING_OPENING,
            f"docstring opens in imperative mood; use "
            f"'{conjugations[verb]}', not '{verb}'",
        )


@lru_cache(maxsize=128)
def _effective_pattern(pyproject: Path | None) -> re.Pattern[str]:
    """Returns the opening-verb regex built from this repo's effective verbs.

    Each verb is escaped before joining: `imperative-verbs-extra` comes from
    repo config, not this module's own hardcoded list, so a configured entry
    containing a regex metacharacter must match itself literally rather than be
    interpreted as one. An empty effective verb set (every verb excluded)
    compiles to a pattern that matches nothing, not one that matches everything
    — `re.compile("^()\\b")` would otherwise match the empty string at the
    start of every summary.
    """
    conjugations = _effective_conjugations(pyproject)
    if conjugations is IMPERATIVE_VERB_CONJUGATIONS:
        return _IMPERATIVE_OPENING_PATTERN
    if not conjugations:
        return re.compile(r"(?!)")
    escaped = (re.escape(verb) for verb in conjugations)
    return re.compile(r"^(" + "|".join(escaped) + r")\b")


@lru_cache(maxsize=128)
def _effective_conjugations(pyproject: Path | None) -> dict[str, str]:
    """Returns the verb-to-conjugation map, adjusted for this repo's config.

    A repo adds its own survey-backed verb via `imperative-verbs-extra`, or
    drops a homograph too risky for its own domain via
    `imperative-verbs-exclude`, tuning RS034 locally instead of editing the
    shared verb list every repo inherits — the same override pattern RS017's
    `banned-imports` and RS033's `filename-extensions` already use. A consuming
    repo excluding every verb (its own plus any extra) is left with an empty
    map.
    """
    table = _repostyle_table(pyproject)
    extra = _string_list(table, "imperative-verbs-extra")
    exclude = frozenset(_string_list(table, "imperative-verbs-exclude"))
    if not extra and not exclude:
        return IMPERATIVE_VERB_CONJUGATIONS
    verbs = dict.fromkeys(
        verb for verb in (*_IMPERATIVE_VERBS, *extra) if verb not in exclude
    )
    return {verb: _conjugate(verb) for verb in verbs}


def check_docstring_terminal_punctuation(
    path: Path, source: str
) -> Iterator[Violation]:
    """Every docstring prose unit must end with terminal punctuation.

    A summary, a body paragraph, and an `Args:`, `Returns:`, `Raises:`, or
    `Yields:` entry each close with `.`, `!`, or `?`, as PEP 257 prescribes for
    the summary and the house style extends to the rest. Code (doctests,
    `Example:` sections, fenced blocks), bullet items, a list-introducing
    colon, and a unit ending in a URL are exempt.
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


def check_unbackticked_code_reference(path: Path, source: str) -> Iterator[Violation]:
    """Flags a code name in docstring prose left without backticks.

    A word in docstring prose that matches a name the module itself binds — a
    parameter, an import, a function or class, an accessed attribute — or one
    of the literals `None`, `True`, and `False` reads as a code reference, and
    the house style sets a code token in single backticks. To stay mechanical
    the check fires only where a word cannot be ordinary English: an
    underscore, a digit, or an interior capital beside a lowercase letter
    (`skip_lines`, `col_offset`, `HttpClient`) marks it as code wherever it
    sits. A literal fires mid-sentence, where a capital `None` is unambiguous,
    but not at a sentence start, where it could open an English clause. A
    plain-lowercase word (a `path` parameter), a Titlecase or all-caps word
    that also reads as English (`Path`, `Note`, `WARNING`), a backticked span,
    a URL, and a doctest are all left alone.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    known = _module_bound_names(tree) | _LITERAL_CONSTANTS
    source_lines = source.splitlines()
    for node in _walk_docstring_owners(tree):
        constant = _docstring_constant(node)
        if constant is None:
            continue
        names: list[str] = []
        for unit in _docstring_prose_units(constant):
            for name in _unbackticked_references(unit, known):
                if name not in names:
                    names.append(name)
        for name in names:
            lineno, col = _name_location(source_lines, constant, name)
            yield Violation(
                lineno,
                col,
                RS_UNBACKTICKED_CODE_REFERENCE,
                f"`{name}` in a docstring reads as a code reference but is not "
                "backticked; wrap it in single backticks",
            )


def fix_docstring_terminal_punctuation(
    path: Path, source: str, skip_lines: frozenset[int] = frozenset()
) -> str:
    """Appends a period to each unterminated docstring prose unit, RS030's fix.

    A summary, body paragraph, or section entry that the rule flags as missing
    terminal punctuation gains a trailing `.` after its content, before the
    closing quote when the quote shares the line. A unit whose line is in
    `skip_lines` is left untouched.

    Returns:
        The source with a period appended to each flagged unit, unchanged when
        nothing appends.
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
    for index, line in _unfenced_md_lines(source):
        match = DOUBLE_BACKTICK_PATTERN.search(line)
        if match:
            yield Violation(
                index + 1,
                match.start() + 1,
                RS_NO_DOUBLE_BACKTICKS,
                "use single backticks, not double, in prose",
            )


def _comment_lines(source: str) -> tuple[dict[int, tuple[int, str]], dict[int, str]]:
    """Splits a source's comments into the standalone and trailing maps.

    The first map keys each whole-line comment's line to its column and text;
    the second keys each line whose comment trails code to that comment's text.
    A comment is standalone when nothing but whitespace precedes it on its
    line.
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
    """Yields every `@dataclass`-decorated class in `tree`."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and _has_dataclass_decorator(node):
            yield node


def _module_bound_names(tree: ast.Module) -> frozenset[str]:
    """Returns every name the module binds, reads, or accesses as an attribute.

    Imports, function and class names, parameters, assignment targets, and
    accessed attributes together over-approximate the names a docstring in the
    module might reference, so a prose word matching one is a candidate for a
    missing backtick. The shape test in `_reads_as_code_reference` drops the
    plain-English collisions this wide net catches.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.alias):
            names.add(node.asname or node.name.split(".")[0])
    return frozenset(names)


def _name_location(
    source_lines: list[str], constant: ast.Constant, name: str
) -> tuple[int, int]:
    """Returns the source position of the first bare `name` in the docstring.

    The scan walks the docstring's own physical lines, dropping backtick spans
    so a backticked mention is skipped, and points the violation at the token
    itself rather than the prose unit that contains it, so the finding lands on
    the right line under `--diff`.
    """
    pattern = re.compile(rf"(?<![\w`]){re.escape(name)}(?![\w`])")
    end = constant.end_lineno or constant.lineno
    for lineno in range(constant.lineno, end + 1):
        stripped = _BACKTICK_SPAN_PATTERN.sub(" ", source_lines[lineno - 1])
        match = pattern.search(stripped)
        if match is not None:
            return lineno, match.start() + 1
    return constant.lineno, constant.col_offset + 1


def _unbackticked_references(unit: _ProseUnit, known: frozenset[str]) -> list[str]:
    """Returns the distinct known names a prose unit uses without backticks."""
    text = _URL_PATTERN.sub(" ", _BACKTICK_SPAN_PATTERN.sub(" ", unit.text))
    if unit.kind == "entry":
        text = _ENTRY_CAPTION_PATTERN.sub("", text)
    found: list[str] = []
    for match in _IDENTIFIER_PATTERN.finditer(text):
        name = match.group()
        if name not in known or name in found:
            continue
        if _reads_as_code_reference(name, text, match.start()):
            found.append(name)
    return found


def _reads_as_code_reference(name: str, text: str, start: int) -> bool:
    """Reports whether `name` at `start` reads as code rather than English.

    A literal reads as code mid-sentence, but at a sentence start its capital
    could open an English clause, so it is exempt there. Any other name fires
    only when its shape rules out an English word: an underscore, a digit, or
    an interior capital beside a lowercase letter (CamelCase). A plain
    lowercase, Titlecase, or all-caps word could be English and is left alone.
    """
    if name in _LITERAL_CONSTANTS:
        return not _at_sentence_start(text, start)
    if "_" in name or any(character.isdigit() for character in name):
        return True
    has_interior_capital = any(character.isupper() for character in name[1:])
    return has_interior_capital and any(character.islower() for character in name)


def _at_sentence_start(text: str, start: int) -> bool:
    """Reports whether the token at `start` opens `text` or a new sentence."""
    before = text[:start].rstrip()
    return not before or before.endswith(_SENTENCE_ENDINGS)


def _docstring_constant(node: ast.AST) -> ast.Constant | None:
    """Returns `node`'s docstring string-literal node, or `None`."""
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
    """Groups a docstring's lines into summary, body, and entry units."""
    segmenter = _DocstringSegmenter()
    for line in _doc_lines(constant):
        segmenter.consume(line)
    segmenter.close()
    return segmenter.units


def _doc_lines(constant: ast.Constant) -> list[_DocLine]:
    """Splits a docstring literal into structure-tagged source lines.

    The first line abuts the opening quote, so it anchors its column at the
    literal and the body margin is taken from the first following non-blank
    line, with every later line's indent measured relative to it. The source
    line is clamped to the literal's physical span, so a docstring carrying
    escaped newlines or built by implicit concatenation still points within
    itself rather than past it.
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


def _docstring_summary_line(docstring: str) -> str:
    """Returns a cleaned `docstring`'s first non-blank line, stripped."""
    return next((line.strip() for line in docstring.splitlines() if line.strip()), "")


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
    """Groups docstring lines into the prose units the rule grades.

    Feed lines in order with `consume`, call `close` after the last, then read
    `units`. The first paragraph is the summary; later margin paragraphs are
    body; a `Note:` section's body is treated as body; an `Args:`-style section
    yields one entry per item; and code, doctests, `Example:` sections,
    bullets, and verbatim lines yield nothing.
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
        """Finishes the open unit, appending it to `units` if non-empty."""
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
        """Routes `line` to its unit, ending the open unit as needed."""
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
        """Starts a new entry on a caption line, or extends the open one.

        An entry opens on a `name:`-style caption at the entry margin; a line
        that carries no caption continues the open entry, whether it wraps at a
        deeper indent or at the entry margin, so a `Returns:` description
        wrapped at one indent stays a single multi-line entry.
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
        """Extends the open summary or body paragraph, or starts a new one."""
        if self._open and self._open_kind in ("summary", "body"):
            self._open.append(line)
            return
        self.close()
        self._open = [line]
        self._open_kind = "summary" if not self._summary_done else "body"

    def _consume_structural(self, line: _DocLine) -> bool:
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
        if line.relative_indent == 0 and text in _SECTION_HEADERS:
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
    """Reports whether the statement after a field is a string docstring."""
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
    """Returns the line of `node`'s first-body-position standalone comment.

    The comment sits directly above the first body statement, with only blank
    lines between, below the definition header. A comment deeper in the body,
    or one trailing the signature, is not returned, so only the leading summary
    position is in scope.
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
    """Flags a module whose first prose line is a comment, not a docstring.

    A leading shebang, coding, or tool-directive line is skipped, so the
    summary comment beneath it is still reached; the first non-directive
    standalone comment then decides, since only the leading position is in
    scope.
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
    """Yields every class and function definition in `tree`."""
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef | ast.ClassDef | ast.FunctionDef):
            yield node


def _terminal_insert_index(line: str, lineno: int, constant: ast.Constant) -> int:
    """Returns the column on `line` just past a prose unit's last content.

    When the closing quote shares the unit's last line, the index lands before
    it; otherwise it lands after the line's last non-space character.
    """
    stripped = line.rstrip()
    if lineno == constant.end_lineno:
        # Match the delimiter by suffix, not `end_col_offset`: that offset is
        # in bytes and misplaces the mark on a line carrying non-ASCII text.
        for delimiter in ('"""', "'''", '"', "'"):
            if stripped.endswith(delimiter):
                return len(stripped[: -len(delimiter)].rstrip())
    return len(stripped)


def _terminal_punctuation_message(kind: str) -> str:
    """Returns the fix message for a missing terminal mark on `kind`."""
    subject = {
        "summary": "docstring summary",
        "body": "docstring body paragraph",
        "entry": "section entry",
    }[kind]
    return f"{subject} should end with terminal punctuation (`.`, `!`, or `?`)"


def _unfenced_md_lines(source: str) -> Iterator[tuple[int, str]]:
    """Yields `(index, line)` for each line outside a fenced code block."""
    in_fence = False
    for index, line in enumerate(source.splitlines()):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            yield index, line


def _walk_docstring_owners(
    tree: ast.AST,
) -> Iterator[ast.AsyncFunctionDef | ast.ClassDef | ast.FunctionDef | ast.Module]:
    for node in ast.walk(tree):
        if isinstance(
            node, ast.AsyncFunctionDef | ast.ClassDef | ast.FunctionDef | ast.Module
        ):
            yield node
