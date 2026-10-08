"""Rules for acronyms and symbol references in prose."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from repostyle._shared import (
    _join_source_lines,
    _parse_python,
    _standalone_comment_blocks,
    find_pyproject,
)
from repostyle.rules._doc_blocks import internal_doc_blocks
from repostyle.rules._docstring_edits import (
    internal_backticks_a_code_symbol,
)
from repostyle.rules._docstring_source import (
    internal_docstring_constant,
    internal_docstring_prose_units,
)
from repostyle.rules._prose_analysis import (
    internal_comment_prose_unit,
    internal_comment_symbol_location,
    internal_name_location,
    internal_sibling_symbol_evidence,
    internal_unbackticked_references,
)
from repostyle.rules._prose_sources import (
    internal_walk_docstring_owners,
)
from repostyle.rules._violation import (
    RS_ACRONYM_CASING_IN_PROSE,
    RS_UNBACKTICKED_SIBLING_SYMBOL,
    Violation,
)
from repostyle.rules.naming import (
    effective_prose_acronyms,
    miscased_acronyms_in_prose,
)


def check_unbackticked_sibling_symbol(path: Path, source: str) -> Iterator[Violation]:
    """Flags a bare code token beside a backticked sibling in one docstring.

    Where a docstring already sets one code symbol in single backticks, a house
    convention holds that its siblings are set the same way, so a bare token
    left in prose reads as an oversight rather than a choice. This check fires
    only on that inconsistency: a docstring must already backtick at least one
    code-shaped token before any bare token in it is considered.

    A bare token qualifies only when its shape rules out ordinary English -- an
    underscore, a digit, or an interior capital beside a lowercase letter
    (`remote_aes`, `col_offset`, `HttpClient`) -- and when the same file offers
    self-contained proof it is a real identifier by carrying it verbatim inside
    a string literal, such as a table or column name in an embedded SQL
    statement. A name the module binds is left to RS036, which flags it whether
    or not a sibling is backticked, so the two rules never fire on one token.
    """
    tree = _parse_python(path, source)
    if tree is None:
        return
    symbols = internal_sibling_symbol_evidence(tree)
    if not symbols:
        return
    source_lines = source.splitlines()
    for node in internal_walk_docstring_owners(tree):
        constant = internal_docstring_constant(node)
        if constant is None:
            continue
        units = internal_docstring_prose_units(constant)
        if not internal_backticks_a_code_symbol(units):
            continue
        bare = dict.fromkeys(
            name
            for unit in units
            for name in internal_unbackticked_references(unit, symbols)
        )
        for name in bare:
            lineno, col = internal_name_location(source_lines, constant, name)
            yield Violation(
                lineno,
                col,
                RS_UNBACKTICKED_SIBLING_SYMBOL,
                f"`{name}` is left bare while a sibling code symbol in the same docstring is backticked; wrap it in single backticks",
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
    symbols = internal_sibling_symbol_evidence(tree)
    if not symbols:
        return
    source_lines = source.splitlines()
    for block in _standalone_comment_blocks(path, source):
        unit = internal_comment_prose_unit(block)
        if not internal_backticks_a_code_symbol([unit]):
            continue
        for name in dict.fromkeys(internal_unbackticked_references(unit, symbols)):
            lineno, col = internal_comment_symbol_location(source_lines, block, name)
            yield Violation(
                lineno,
                col,
                RS_UNBACKTICKED_SIBLING_SYMBOL,
                f"`{name}` is left bare while a sibling code symbol in the same comment is backticked; wrap it in single backticks",
            )


def check_acronym_casing_in_docstrings(path: Path, source: str) -> Iterator[Violation]:
    """Flags a known acronym miscased in docstring or Javadoc prose.

    A whole word that case-insensitively matches a known acronym but is not in
    its canonical casing is flagged and, under `--fix`, rewritten to it (`ipv6`
    and `IPV6` to `IPv6`, `Nat` to `NAT`). The resolved set is the shipped
    acronyms plus `acronyms-extra` minus `acronyms-exclude`, sharing RS001's
    config keys, less a small set whose lowercased form is a common English
    word (`SMART`). A match is whole-word only, so a substring (`ID` in
    `identify`, `NAT` in `nation`), a hyphenated compound (`fhir-ingestor`),
    and a correctly-cased occurrence are left alone. So is code: a backtick
    span, a Javadoc inline tag, a URL, and the parameter caption leading an
    `Args:` entry or a block tag, whose name the author spells.
    """
    for lineno, offset, found, canonical in _doc_acronym_faults(path, source):
        yield Violation(
            lineno,
            offset + 1,
            RS_ACRONYM_CASING_IN_PROSE,
            f"docstring miscases the acronym '{canonical}' as '{found}'; write '{canonical}'",
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
    source_lines = source.splitlines()
    changed = False
    for lineno, offset, found, canonical in _doc_acronym_faults(path, source):
        if lineno in skip_lines:
            continue
        line = source_lines[lineno - 1]
        if line[offset : offset + len(found)] == found:
            source_lines[lineno - 1] = (
                line[:offset] + canonical + line[offset + len(found) :]
            )
            changed = True
    return _join_source_lines(source, source_lines) if changed else source


def _doc_acronym_faults(path: Path, source: str) -> Iterator[tuple[int, int, str, str]]:
    """Yields `(lineno, offset, found, canonical)` for each miscased acronym.

    Scans each prose line of each doc block, confined to the block's own
    columns with code spans and captions blanked, so a one-line signature, a
    trailing comment, and a parameter named for a lowercased acronym (`url:`)
    are not mistaken for prose to correct.
    """
    canonical_casing = effective_prose_acronyms(find_pyproject(path))
    if not canonical_casing:
        return
    for block in internal_doc_blocks(path, source):
        for lineno, line in block.scan_lines:
            for offset, found, canonical in miscased_acronyms_in_prose(
                line, canonical_casing
            ):
                yield (lineno, offset, found, canonical)
