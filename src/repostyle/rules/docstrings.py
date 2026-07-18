"""Docstring and markdown prose rules.

The placement rules move a summary or field comment that documents a unit into
the docstring slot this package's own doc-content rules can see. The form rules
hold a docstring to its own contract: no `Attributes:` block, single not double
backticks, a backticked code reference with no suffix glued to it, no filler or
imperative-mood opening, and terminal punctuation on every prose unit.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from collections.abc import Iterable, Iterator
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

from repostyle._comments import COMMENT_SUFFIXES, extract_comments
from repostyle._shared import (
    _comment_text,
    _is_directive_comment,
    _is_prose_comment,
    _join_source_lines,
    _parse_python,
    _repostyle_table,
    _standalone_comment_blocks,
    _string_list,
    _temporal_markers,
    _terminal_punctuation_fault,
    find_pyproject,
)
from repostyle.rules._violation import (
    RS_ACRONYM_CASING_IN_PROSE,
    RS_FIELD_COMMENT_AS_DOCSTRING,
    RS_FILLER_DOCSTRING_OPENING,
    RS_GLUED_CODE_SPAN,
    RS_IMPERATIVE_DOCSTRING_OPENING,
    RS_LOWERCASE_ENTRY_DESCRIPTION,
    RS_NO_ATTRIBUTES_BLOCK,
    RS_NO_DOUBLE_BACKTICKS,
    RS_SUMMARY_COMMENT_AS_DOCSTRING,
    RS_TEMPORAL_MARKER,
    RS_TERMINAL_PUNCTUATION,
    RS_UNBACKTICKED_CODE_REFERENCE,
    RS_UNBACKTICKED_SIBLING_SYMBOL,
    Violation,
)
from repostyle.rules.imperative_verbs import (
    IMPERATIVE_OPENING_PATTERN,
    IMPERATIVE_VERB_CONJUGATIONS,
    IMPERATIVE_VERBS,
    conjugate,
)
from repostyle.rules.naming import (
    effective_prose_acronyms,
    miscased_acronyms_in_prose,
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
# A backtick-delimited span or a URI, both dropped before RS036 scans a unit: a
# name already in code font, or one sitting inside a `gs://`, `https://`, or
# other scheme's path, is not a bare prose reference.
_BACKTICK_SPAN_PATTERN = re.compile(r"`[^`]*`")
_URI_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]*://\S+")
# A Python identifier, the token RS036 tests against the known-name set
_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# An entry unit leads with its own `name:` or `name (type):` caption, which
# documents the name rather than referencing it, so RS036 strips the caption
# before scanning.
_ENTRY_CAPTION_PATTERN = re.compile(r"^\S+(?:\s*\([^)]*\))?:\s*")
# The leading identifier of an entry description, possibly dotted
# (`json.dumps`): RS047 reads its shape to tell an inherently-lowercase code
# token from a lowercase prose word. A dot only extends the token when a word
# follows it, so a sentence-final `bar.` yields the bare `bar`, not a false
# dotted path.
_LEADING_TOKEN_PATTERN = re.compile(r"[A-Za-z_]\w*(?:\.\w+)*")
# A pluralized all-caps acronym (`UIDs`, `URLs`, `IDs`): an acronym reads as
# English whether bare (`URL`) or plural, so the trailing `s` — its only
# lowercase letter — must not make the token look like code.
_PLURAL_ACRONYM_PATTERN = re.compile(r"[A-Z]{2,}s")
_SENTENCE_ENDINGS = (".", "!", "?")
_GLUED_SPAN_MESSAGE = (
    "a code span carries a glued suffix; move the suffix outside the backticks"
)


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


def check_glued_code_span_in_docstrings(path: Path, source: str) -> Iterator[Violation]:
    """Docstring prose may not glue an inflection to a code span.

    A code span sets a name in code font, so an English suffix run straight
    onto its closing backtick — a possessive apostrophe-s, a plural, or a verb
    ending — reads as part of the identifier and breaks the span in rendered
    Markdown. The check fires on a closing backtick followed at once by a
    letter or an apostrophe, and leaves a hyphenated compound such as `-safe`
    alone, since that keeps the span ending on a word boundary. The rule warns
    and has no automatic fix; the remedy is to move the suffix outside the
    span.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    source_lines = source.splitlines()
    for node in _walk_docstring_owners(tree):
        constant = _docstring_constant(node)
        if constant is None:
            continue
        start = constant.lineno
        end = constant.end_lineno or start
        # Join the docstring's physical lines so a code span crossing a line
        # break pairs as one span; scanning each line alone would pair a
        # wrapped span's trailing backtick with the next span's opening one. A
        # line outside the segmenter's prose units — inside a fence or
        # `Example:` section, or a doctest line — is blanked to its width so
        # its backticks neither pair nor draw a finding, as RS030 and RS036
        # also skip those lines, while the blank preserves the column math
        # below. The blanking is skipped only for an implicitly-concatenated
        # literal, whose adjacent pieces decode to fewer lines than the literal
        # spans and so collapse the value-to-physical mapping the blanking
        # relies on; such a literal carries no code section, so all its lines
        # are scanned. A single literal — even one with an escaped newline,
        # which only adds value lines — keeps the blanking so a fenced or
        # `Example:` region stays excluded.
        concatenated = constant.value.count("\n") < end - start
        prose_lines = _docstring_prose_line_numbers(constant)
        block = "\n".join(
            line if concatenated or lineno in prose_lines else " " * len(line)
            for lineno, line in enumerate(source_lines[start - 1 : end], start)
        )
        for offset in _glued_code_span_columns(block):
            before = block[:offset]
            yield Violation(
                start + before.count("\n"),
                offset - before.rfind("\n"),
                RS_GLUED_CODE_SPAN,
                _GLUED_SPAN_MESSAGE,
            )


def check_glued_code_span_in_comments(path: Path, source: str) -> Iterator[Violation]:
    """A comment may not glue an English suffix onto a code span.

    The same rule the docstring check applies holds for a comment: a suffix run
    onto a code span's closing backtick reads as part of the identifier. A
    standalone and a trailing comment are covered alike, across the Python,
    TOML, and YAML comments `extract_comments` handles — tokenizing a
    non-Python file as Python here would raise on its first irregular indent.
    """
    if path.suffix not in COMMENT_SUFFIXES:
        return
    for comment in extract_comments(path, source):
        for offset in _glued_code_span_columns(comment.string):
            yield Violation(
                comment.lineno,
                comment.column + offset + 1,
                RS_GLUED_CODE_SPAN,
                _GLUED_SPAN_MESSAGE,
            )


def check_glued_code_span_in_md(path: Path, source: str) -> Iterator[Violation]:
    """Markdown prose may not glue an inflection to a code span."""
    if path.suffix != ".md":
        return
    for index, line in _unfenced_md_lines(source):
        for offset in _glued_code_span_columns(line):
            yield Violation(
                index + 1, offset + 1, RS_GLUED_CODE_SPAN, _GLUED_SPAN_MESSAGE
            )


def _docstring_prose_line_numbers(constant: ast.Constant) -> frozenset[int]:
    """Returns the source lines the docstring's prose units occupy.

    The segmenter that groups a docstring into summary, body, entry, and bullet
    units already drops a fenced block, an `Example:` section, a doctest, and a
    verbatim line, so the union of its units' source lines is exactly the prose
    the glued-span check should scan.
    """
    return frozenset(
        lineno for unit in _docstring_prose_units(constant) for lineno in unit.linenos
    )


def _glued_code_span_columns(text: str) -> Iterator[int]:
    """Yields the 0-based column of each suffix glued to a code span in `text`.

    Real spans are found with `finditer`, which consumes each span so backticks
    pair left to right; matching the trailing character in the pattern instead
    would let a failed match restart on a closing backtick and read the gap
    between two spans as a span of its own. A letter or an apostrophe abutting
    a span's closing backtick is the glued suffix; a hyphen (a compound like
    `-typed`) and any other character are left alone.
    """
    for match in _BACKTICK_SPAN_PATTERN.finditer(text):
        end = match.end()
        if end - match.start() <= 2 or end >= len(text):
            continue
        # A curly apostrophe is a real possessive to flag, so it stays literal
        # here despite RUF001's ambiguous-character warning.
        if text[end].isalpha() or text[end] in "'’":  # noqa: RUF001
            yield end


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
    r"""Returns the opening-verb regex built from this repo's effective verbs.

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
        return IMPERATIVE_OPENING_PATTERN
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
        verb for verb in (*IMPERATIVE_VERBS, *extra) if verb not in exclude
    )
    return {verb: conjugate(verb) for verb in verbs}


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
            if unit.kind == "bullet":
                continue
            if _terminal_punctuation_fault(unit.text, is_prose=True) is None:
                continue
            yield Violation(
                unit.lineno,
                unit.col,
                RS_TERMINAL_PUNCTUATION,
                _terminal_punctuation_message(unit.kind),
            )


def check_lowercase_entry_description(path: Path, source: str) -> Iterator[Violation]:
    """A Google-section entry's description opens with a capital letter.

    An `Args:`, `Returns:`, `Raises:`, or `Yields:` entry states its
    description as a full sentence, so it opens with a capital just as RS030
    requires it to close with a period — the two rules are the opening-capital
    and closing-period halves of the same full-sentence convention. `bar: A
    bar.`, not `bar: a bar.`; `NotFoundError: If a foo is not found.`, not
    `NotFoundError: if a foo is not found.`.

    Only a lowercase ASCII prose letter opening the description fires. A
    description opening with a backtick code span, an inherently-lowercase code
    token (a parameter name or a dotted path like `json.dumps`), a digit, or
    any other non-letter is left alone, so a legitimately lowercase opener does
    not draw a false finding. An empty description is skipped.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    source_lines = source.splitlines()
    for node in _walk_docstring_owners(tree):
        constant = _docstring_constant(node)
        if constant is None:
            continue
        for unit in _docstring_prose_units(constant):
            if unit.kind != "entry":
                continue
            if not _opens_with_lowercase_prose(_entry_description(unit.text)):
                continue
            lineno = unit.linenos[0]
            line = source_lines[lineno - 1]
            yield Violation(
                lineno,
                len(line) - len(line.lstrip()) + 1,
                RS_LOWERCASE_ENTRY_DESCRIPTION,
                "a section entry description opens in lowercase; begin it with "
                "a capital letter",
            )


def check_docstring_temporal_markers(path: Path, source: str) -> Iterator[Violation]:
    """Flags a temporal or edit-narrative marker in docstring prose.

    A curated set of phrases — naming what the code once did, or how a change
    was reached — narrates the edit rather than the unit's present contract, so
    it belongs in the commit message, not durable docstring prose. This is the
    common source of an agent leaking the session's design discussion and the
    diff's story into the code. A marker quoted inside a backtick span is a
    referenced token, not narration, and is left alone. Each prose unit —
    summary, body paragraph, or section entry — is scanned; a code span,
    doctest, or `Example:` block is not. This is the mechanical floor under the
    `common-style-review` prose-economy lens, which judges the ambiguous cases
    this tight set deliberately leaves out.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    for node in _walk_docstring_owners(tree):
        constant = _docstring_constant(node)
        if constant is None:
            continue
        for unit in _docstring_prose_units(constant):
            for marker in _temporal_markers(unit.text):
                yield Violation(
                    unit.lineno,
                    unit.col,
                    RS_TEMPORAL_MARKER,
                    f"docstring narrates the edit history with '{marker}'; "
                    "state the code's current contract, not how it changed",
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
    a URI, and a doctest are all left alone.
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


def check_unbackticked_sibling_symbol(path: Path, source: str) -> Iterator[Violation]:
    """Flags a bare code token beside a backticked sibling in one docstring.

    Where a docstring already sets one code symbol in single backticks, a house
    convention holds that its siblings are set the same way, so a bare token
    left in prose reads as an oversight rather than a choice. This check fires
    only on that inconsistency: a docstring must already backtick at least one
    code-shaped token before any bare token in it is considered.

    A bare token qualifies only when its shape rules out ordinary English — an
    underscore, a digit, or an interior capital beside a lowercase letter
    (`remote_aes`, `col_offset`, `HttpClient`) — and when the same file offers
    self-contained proof it is a real identifier by carrying it verbatim inside
    a string literal, such as a table or column name in an embedded SQL
    statement. A name the module binds is left to RS036, which flags it whether
    or not a sibling is backticked, so the two rules never fire on one token.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    symbols = _sibling_symbol_evidence(tree)
    if not symbols:
        return
    source_lines = source.splitlines()
    for node in _walk_docstring_owners(tree):
        constant = _docstring_constant(node)
        if constant is None:
            continue
        units = _docstring_prose_units(constant)
        if not _backticks_a_code_symbol(units):
            continue
        bare = dict.fromkeys(
            name for unit in units for name in _unbackticked_references(unit, symbols)
        )
        for name in bare:
            lineno, col = _name_location(source_lines, constant, name)
            yield Violation(
                lineno,
                col,
                RS_UNBACKTICKED_SIBLING_SYMBOL,
                f"`{name}` is left bare while a sibling code symbol in the same "
                "docstring is backticked; wrap it in single backticks",
            )


def check_unbackticked_sibling_symbol_in_comments(
    path: Path, source: str
) -> Iterator[Violation]:
    """Flags a bare code token beside a backticked sibling in a comment.

    RS039's docstring rule carried to a contiguous run of `#` comment lines:
    where the block already backticks a code-shaped token, a bare sibling token
    left in it reads as an oversight rather than a choice. The two guards hold
    unchanged: the bare token must be distinctive in shape and must recur
    verbatim inside a string literal in the file, so the finding rests on
    self-contained evidence rather than a guess. A name the module binds stays
    RS036's. Only Python is scanned, since the string-literal proof is read
    from the file's own AST.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    symbols = _sibling_symbol_evidence(tree)
    if not symbols:
        return
    source_lines = source.splitlines()
    for block in _standalone_comment_blocks(path, source):
        unit = _comment_prose_unit(block)
        if not _backticks_a_code_symbol([unit]):
            continue
        for name in dict.fromkeys(_unbackticked_references(unit, symbols)):
            lineno, col = _comment_symbol_location(source_lines, block, name)
            yield Violation(
                lineno,
                col,
                RS_UNBACKTICKED_SIBLING_SYMBOL,
                f"`{name}` is left bare while a sibling code symbol in the same "
                "comment is backticked; wrap it in single backticks",
            )


def check_acronym_casing_in_docstrings(path: Path, source: str) -> Iterator[Violation]:
    """Flags a known acronym miscased in docstring prose.

    A whole word in docstring prose that case-insensitively matches a known
    acronym but is not in the acronym's canonical casing is flagged and, under
    `--fix`, rewritten to it (`ipv6` and `IPV6` to `IPv6`, `Nat` to `NAT`). The
    resolved set is the shipped acronyms plus `acronyms-extra` minus
    `acronyms-exclude`, sharing RS001's config keys, less a small set whose
    lowercased form is a common English word (`SMART`). A match is whole-word
    only, so a substring (`ID` in `identify`, `NAT` in `nation`) is left alone,
    as is a hyphenated compound (`fhir-ingestor`), a correctly-cased
    occurrence, a token inside a backtick span or a URL, and an `Args:` entry's
    leading parameter caption, whose name is code the author spells.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    canonical_casing = effective_prose_acronyms(find_pyproject(path))
    if not canonical_casing:
        return
    source_lines = source.splitlines()
    for node in _walk_docstring_owners(tree):
        constant = _docstring_constant(node)
        if constant is None:
            continue
        for lineno, offset, found, canonical in _docstring_acronym_faults(
            constant, source_lines, canonical_casing
        ):
            yield Violation(
                lineno,
                offset + 1,
                RS_ACRONYM_CASING_IN_PROSE,
                f"docstring miscases the acronym '{canonical}' as '{found}'; "
                f"write '{canonical}'",
            )


def fix_acronym_casing_in_docstrings(
    path: Path, source: str, skip_lines: frozenset[int] = frozenset()
) -> str:
    """Rewrites each miscased acronym in docstring prose, the RS049 fix.

    Each occurrence the docstring check flags is replaced in place with the
    acronym's canonical casing; the rewrite is case-only and never changes
    length, so the surrounding line is otherwise untouched. A unit whose line
    is in `skip_lines` is left alone.

    Returns:
        The source with each flagged acronym recased, unchanged when nothing
        recases.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return source
    canonical_casing = effective_prose_acronyms(find_pyproject(path))
    if not canonical_casing:
        return source
    source_lines = source.splitlines()
    changed = False
    for node in _walk_docstring_owners(tree):
        constant = _docstring_constant(node)
        if constant is None:
            continue
        for lineno, offset, found, canonical in _docstring_acronym_faults(
            constant, source_lines, canonical_casing
        ):
            if lineno in skip_lines:
                continue
            line = source_lines[lineno - 1]
            if line[offset : offset + len(found)] == found:
                source_lines[lineno - 1] = (
                    line[:offset] + canonical + line[offset + len(found) :]
                )
                changed = True
    return _join_source_lines(source, source_lines) if changed else source


def _docstring_acronym_faults(
    constant: ast.Constant, source_lines: list[str], canonical_casing: dict[str, str]
) -> Iterator[tuple[int, int, str, str]]:
    """Yields `(lineno, offset, found, canonical)` for each miscased acronym.

    Scans each source line the docstring's prose units occupy — the segmenter
    already drops fences, doctests, and `Example:` sections — and blanks an
    entry unit's leading `name:` caption on its first line, so a parameter
    named for a lowercased acronym (`url:`) is not mistaken for prose to
    correct.
    """
    units = _docstring_prose_units(constant)
    prose_lines = frozenset(lineno for unit in units for lineno in unit.linenos)
    caption_lines = {unit.linenos[0] for unit in units if unit.kind == "entry"}
    for lineno in sorted(prose_lines):
        line = source_lines[lineno - 1]
        scanned = _blank_entry_caption(line) if lineno in caption_lines else line
        for offset, found, canonical in miscased_acronyms_in_prose(
            scanned, canonical_casing
        ):
            yield lineno, offset, found, canonical


def _blank_entry_caption(line: str) -> str:
    """Blanks an entry line's leading `name:` caption to equal-length spaces.

    The blanking preserves every following character's offset, so a token found
    past the caption still indexes the original `line`. A line carrying no
    caption is returned unchanged.
    """
    stripped = line.lstrip()
    match = _ENTRY_CAPTION_PATTERN.match(stripped)
    if match is None:
        return line
    indent = len(line) - len(stripped)
    end = indent + match.end()
    return line[:indent] + " " * (end - indent) + line[end:]


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
            if unit.kind == "bullet" or unit.lineno in skip_lines:
                continue
            if _terminal_punctuation_fault(unit.text, is_prose=True) != "missing":
                continue
            line = source_lines[unit.lineno - 1]
            index = _terminal_insert_index(line, unit.lineno, constant)
            source_lines[unit.lineno - 1] = f"{line[:index]}.{line[index:]}"
            changed = True
    return _join_source_lines(source, source_lines) if changed else source


def _backticks_a_code_symbol(units: list[_ProseUnit]) -> bool:
    """Reports whether a docstring already backticks a code-shaped token.

    A backticked span whose content holds a distinctive identifier is the
    consistency trigger: it shows the author backticks code in this docstring,
    so a bare sibling token is an inconsistency rather than deliberate prose.
    The caller passes only the prose units the bare-token scan reads, so a
    backtick inside a doctest or `Example:` block, which the scan skips, never
    trips the trigger.
    """
    return any(
        _is_distinctive_code_token(match.group())
        for unit in units
        for span in _BACKTICK_SPAN_PATTERN.finditer(unit.text)
        for match in _IDENTIFIER_PATTERN.finditer(span.group().strip("`"))
    )


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


# A standalone comment's `(column, text)`, keyed elsewhere by its line number
_StandaloneComment = tuple[int, str]


def _comment_lines(source: str) -> tuple[dict[int, _StandaloneComment], dict[int, str]]:
    """Splits a source's comments into the standalone and trailing maps.

    The first map keys each whole-line comment's line to its column and text;
    the second keys each line whose comment trails code to that comment's text.
    A comment is standalone when nothing but whitespace precedes it on its
    line.
    """
    source_lines = source.splitlines()
    standalone: dict[int, _StandaloneComment] = {}
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


def _comment_prose_unit(block: list[tuple[int, int, str]]) -> _ProseUnit:
    """Joins a comment block's lines into one prose unit to scan."""
    text = " ".join(_comment_text(string) for _, _, string in block)
    lineno, column, _ = block[0]
    linenos = tuple(line for line, _, _ in block)
    return _ProseUnit("body", lineno, column + 1, text, linenos)


def _comment_symbol_location(
    source_lines: list[str], block: list[tuple[int, int, str]], name: str
) -> tuple[int, int]:
    """Returns the position of the first bare `name` in a comment block."""
    linenos = [line for line, _, _ in block]
    located = _first_bare_token(source_lines, linenos, name)
    lineno, column, _ = block[0]
    return located or (lineno, column + 1)


def _dataclass_classes(tree: ast.Module) -> Iterator[ast.ClassDef]:
    """Yields every `@dataclass`-decorated class in `tree`."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and _has_dataclass_decorator(node):
            yield node


def _entry_description(text: str) -> str:
    """Returns an entry's description, the text after its `name:` caption.

    An `Args:`/`Raises:`/`Yields:` entry leads with a `name:` or `name
    (type):` caption naming the entry rather than describing it, so the caption
    is stripped. A `Returns:`/`Yields:` entry with no name carries no caption,
    so its whole line is the description and is returned unchanged.
    """
    return _ENTRY_CAPTION_PATTERN.sub("", text, count=1).strip()


def _opens_with_lowercase_prose(description: str) -> bool:
    """Reports whether an entry description opens with a lowercase prose word.

    A description opening with a lowercase ASCII letter is a prose word unless
    its leading token is an inherently-lowercase code token — a dotted path or
    a distinctive-shaped identifier (an underscore, a digit, or an interior
    capital) — which reads as code and is left alone. An empty description, or
    one opening with a backtick, a digit, an uppercase letter, or any other
    non-letter, does not fire.
    """
    if not description or not ("a" <= description[0] <= "z"):
        return False
    match = _LEADING_TOKEN_PATTERN.match(description)
    token = match.group() if match else ""
    return "." not in token and not _is_distinctive_code_token(token)


def _sibling_symbol_evidence(tree: ast.AST) -> frozenset[str]:
    """Returns the string-literal tokens proving a bare prose word is code.

    A distinctive token carried verbatim inside a non-docstring string literal
    is self-contained proof, in the file itself, that a matching bare word in a
    docstring or comment names a real identifier. A name the module binds is
    left to RS036, so subtracting the bound names keeps the two rules from
    flagging one token.
    """
    docstring_ids = frozenset(
        id(constant)
        for node in _walk_docstring_owners(tree)
        if (constant := _docstring_constant(node)) is not None
    )
    return _string_literal_symbols(tree, docstring_ids) - _module_bound_names(tree)


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
    end = constant.end_lineno or constant.lineno
    located = _first_bare_token(source_lines, range(constant.lineno, end + 1), name)
    return located or (constant.lineno, constant.col_offset + 1)


def _string_literal_symbols(
    tree: ast.AST, docstring_ids: frozenset[int]
) -> frozenset[str]:
    """Returns the distinctive identifier tokens found in string literals.

    Scans every string constant that is not itself a docstring — an embedded
    SQL statement, a log line, a format string — and collects the identifier
    tokens whose shape marks them as code. A token appearing here is proof, in
    the file itself, that a matching bare word in a docstring names a real
    identifier rather than reading as English.
    """
    symbols: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstring_ids
        ):
            for match in _IDENTIFIER_PATTERN.finditer(node.value):
                if _is_distinctive_code_token(match.group()):
                    symbols.add(match.group())
    return frozenset(symbols)


def _unbackticked_references(unit: _ProseUnit, known: frozenset[str]) -> list[str]:
    """Returns the distinct known names a prose unit uses without backticks."""
    text = _URI_PATTERN.sub(" ", _BACKTICK_SPAN_PATTERN.sub(" ", unit.text))
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
        return not _begins_sentence(text, start)
    return _is_distinctive_code_token(name)


def _begins_sentence(text: str, start: int) -> bool:
    """Reports whether the token at `start` begins `text` or a new sentence."""
    before = text[:start].rstrip()
    return not before or before.endswith(_SENTENCE_ENDINGS)


def _docstring_constant(node: ast.AST) -> ast.Constant | None:
    """Returns the docstring string-literal node of `node`, or `None`."""
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
    """Returns the first non-blank line of a cleaned `docstring`, stripped."""
    return next((line.strip() for line in docstring.splitlines() if line.strip()), "")


def _first_bare_token(
    source_lines: list[str], linenos: Iterable[int], name: str
) -> tuple[int, int] | None:
    """Returns the line and 1-based column of the first unbackticked `name`.

    Backtick spans are dropped before the search, so a mention already in code
    font is skipped and the position points at the bare token a fix must wrap.
    Returns `None` when no bare mention sits on the given lines.
    """
    pattern = re.compile(rf"(?<![\w`]){re.escape(name)}(?![\w`])")
    for lineno in linenos:
        stripped = _BACKTICK_SPAN_PATTERN.sub(" ", source_lines[lineno - 1])
        match = pattern.search(stripped)
        if match is not None:
            return lineno, match.start() + 1
    return None


def _is_distinctive_code_token(name: str) -> bool:
    """Reports whether a token's shape rules out an ordinary English word.

    An underscore, a digit, or an interior capital beside a lowercase letter
    (CamelCase) marks a token as code wherever it sits. A plain lowercase,
    Titlecase, or all-caps word could be English and is not distinctive, and
    neither is a pluralized all-caps acronym (`UIDs`, `URLs`), whose only
    lowercase letter is the trailing `s`.
    """
    if "_" in name or any(character.isdigit() for character in name):
        return True
    if _PLURAL_ACRONYM_PATTERN.fullmatch(name):
        return False
    has_interior_capital = any(character.isupper() for character in name[1:])
    return has_interior_capital and any(character.islower() for character in name)


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
    yields one entry per item; a bullet yields a one-line bullet unit; and
    code, doctests, `Example:` sections, and verbatim lines yield nothing.
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
        linenos = tuple(line.lineno for line in self._open)
        self.units.append(
            _ProseUnit(self._open_kind, last.lineno, last.column + 1, text, linenos)
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
            # A bullet is prose the code-reference and glued-span rules scan,
            # so it becomes its own unit; the terminal-punctuation rule skips a
            # `bullet` unit, since a list item need not close with a period.
            self.units.append(
                _ProseUnit(
                    "bullet", line.lineno, line.column + 1, line.text, (line.lineno,)
                )
            )
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
    """`summary`, `body`, `entry`, or `bullet`."""
    lineno: int
    """Source line the unit's terminal punctuation sits on."""
    col: int
    """1-based column the violation points at."""
    text: str
    """The unit's lines joined into one string."""
    linenos: tuple[int, ...]
    """The source lines the unit's prose occupies."""


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
    """Returns the line of the first-position standalone comment in `node`.

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
