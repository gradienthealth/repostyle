"""Finds bullet, entry, and symbol evidence in prose units."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from functools import lru_cache

from repostyle._shared import (
    _LIST_ITEM_PATTERN,
    _blank_prose_spans,
    _comment_text,
    _has_sentence_boundary,
    _walk_tree,
)
from repostyle.rules._docstring_source import (
    InternalBACKTICK_SPAN_PATTERN,
    InternalBulletItem,
    internal_docstring_constant,
    internal_first_bare_token,
    internal_is_distinctive_code_token,
    internal_reads_as_code_reference,
)
from repostyle.rules._prose_sources import (
    internal_walk_docstring_owners,
)
from repostyle.rules._prose_units import (
    InternalProseUnit,
    internal_has_dataclass_decorator,
)
from repostyle.rules._violation import (
    RS_BULLET_ITEM_CASING,
    Violation,
)


def internal_comment_prose_unit(block: list[tuple[int, int, str]]) -> InternalProseUnit:
    """Joins a comment block's lines into one prose unit to scan."""
    text = " ".join((_comment_text(string) for _, _, string in block))
    lineno, column, _ = block[0]
    linenos = tuple((line for line, _, _ in block))
    return InternalProseUnit("body", lineno, column + 1, text, linenos)


def internal_comment_symbol_location(
    source_lines: list[str], block: list[tuple[int, int, str]], name: str
) -> tuple[int, int]:
    """Finds the first bare `name` in a comment block.

    Returns:
        The 1-based line and column of the name or the block start.
    """
    linenos = [line for line, _, _ in block]
    located = internal_first_bare_token(source_lines, linenos, name)
    lineno, column, _ = block[0]
    return located or (lineno, column + 1)


def internal_dataclass_classes(tree: ast.Module) -> Iterator[ast.ClassDef]:
    """Yields every `@dataclass`-decorated class in `tree`."""
    for node in _walk_tree(tree):
        if isinstance(node, ast.ClassDef) and internal_has_dataclass_decorator(node):
            yield node


def internal_docstring_bullet_lists(
    units: list[InternalProseUnit], source_lines: list[str]
) -> list[list[InternalBulletItem]]:
    """Groups a docstring's bullet units into the lists RS053 judges.

    A maximal run of consecutive bullet units whose first lines share one
    indent is a list; a non-bullet unit or an indent change ends the run, so a
    nested deeper-indented list stands on its own. A blank line yields no unit,
    so blank-separated items still group into one list.
    """
    lists: list[list[InternalBulletItem]] = []
    run: list[InternalBulletItem] = []
    run_indent = -1
    for unit in units:
        if unit.kind != "bullet":
            if run:
                lists.append(run)
            run = []
            continue
        lineno = unit.linenos[0]
        line = source_lines[lineno - 1]
        indent = len(line) - len(line.lstrip())
        if run and indent != run_indent:
            lists.append(run)
            run = []
        if not run:
            run_indent = indent
        run.append(InternalBulletItem(lineno, indent + 1, unit.text))
    if run:
        lists.append(run)
    return lists


def internal_entry_description(text: str) -> str:
    """Returns an entry's description, the text after its `name:` caption.

    An `Args:`/`Raises:`/`Yields:` entry leads with a `name:` or `name
    (type):` caption naming the entry rather than describing it, so the caption
    is stripped. A `Returns:`/`Yields:` entry with no name carries no caption,
    so its whole line is the description and is returned unchanged.
    """
    return InternalENTRY_CAPTION_PATTERN.sub("", text, count=1).strip()


def internal_miscased_bullet_items(
    items: list[InternalBulletItem],
) -> Iterator[Violation]:
    """Yields RS053's violation for each lowercase item in a prose-cased list.

    The list must be sentence-cased when any of its items runs more than one
    sentence; each item that then opens with a lowercase prose word draws one
    violation at its marker.
    """
    texts = [_LIST_ITEM_PATTERN.sub("", item.text, count=1) for item in items]
    if not any(_has_sentence_boundary(_blank_prose_spans(text)) for text in texts):
        return
    for item, text in zip(items, texts, strict=True):
        if internal_opens_with_lowercase_prose(text):
            yield Violation(
                item.lineno, item.col, RS_BULLET_ITEM_CASING, _BULLET_CASING_MESSAGE
            )


_BULLET_CASING_MESSAGE = "a bullet item in a multi-sentence list opens in lowercase; begin each item with a capital letter"


def internal_opens_with_lowercase_prose(description: str) -> bool:
    """Reports whether an entry description opens with a lowercase prose word.

    A description opening with a lowercase ASCII letter is a prose word unless
    its leading token is an inherently-lowercase code token -- a dotted path or
    a distinctive-shaped identifier (an underscore, a digit, or an interior
    capital) -- which reads as code and is left alone. An empty description, or
    one opening with a backtick, a digit, an uppercase letter, or any other
    non-letter, does not fire.
    """
    if not description or not "a" <= description[0] <= "z":
        return False
    match = _LEADING_TOKEN_PATTERN.match(description)
    token = match.group() if match else ""
    return "." not in token and (not internal_is_distinctive_code_token(token))


_LEADING_TOKEN_PATTERN = re.compile("[A-Za-z_]\\w*(?:\\.\\w+)*")


@lru_cache(maxsize=128)
def internal_sibling_symbol_evidence(tree: ast.AST) -> frozenset[str]:
    """Returns the string-literal tokens proving a bare prose word is code.

    A distinctive token carried verbatim inside a non-docstring string literal
    is self-contained proof, in the file itself, that a matching bare word in a
    docstring or comment names a real identifier. A name the module binds is
    left to RS036, so subtracting the bound names keeps the two rules from
    flagging one token.
    """
    docstring_ids = frozenset(
        id(constant)
        for node in internal_walk_docstring_owners(tree)
        if (constant := internal_docstring_constant(node)) is not None
    )
    return _string_literal_symbols(tree, docstring_ids) - internal_module_bound_names(
        tree
    )


@lru_cache(maxsize=128)
def internal_module_bound_names(tree: ast.Module) -> frozenset[str]:
    """Returns every name the module binds, reads, or accesses as an attribute.

    Imports, function and class names, parameters, assignment targets, and
    accessed attributes together over-approximate the names a docstring in the
    module might reference, so a prose word matching one is a candidate for a
    missing backtick. The shape test in `_reads_as_code_reference` drops the
    plain-English collisions this wide net catches.
    """
    names: set[str] = set()
    for node in _walk_tree(tree):
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


def internal_name_location(
    source_lines: list[str], constant: ast.Constant, name: str
) -> tuple[int, int]:
    """Finds the source position of the first bare `name` in the docstring.

    The scan walks the docstring's own physical lines, dropping backtick spans
    so a backticked mention is skipped, and points the violation at the token
    itself rather than the prose unit that contains it, so the finding lands on
    the right line under `--diff`.

    Returns:
        The 1-based line and column of the name or the docstring start.
    """
    end = constant.end_lineno or constant.lineno
    located = internal_first_bare_token(
        source_lines, range(constant.lineno, end + 1), name
    )
    return located or (constant.lineno, constant.col_offset + 1)


def _string_literal_symbols(
    tree: ast.AST, docstring_ids: frozenset[int]
) -> frozenset[str]:
    """Returns the distinctive identifier tokens found in string literals.

    Scans every string constant that is not itself a docstring -- an embedded
    SQL statement, a log line, a format string -- and collects the identifier
    tokens whose shape marks them as code. A token appearing here is proof, in
    the file itself, that a matching bare word in a docstring names a real
    identifier rather than reading as English.
    """
    symbols: set[str] = set()
    for node in _walk_tree(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and (id(node) not in docstring_ids)
        ):
            for match in InternalIDENTIFIER_PATTERN.finditer(node.value):
                if internal_is_distinctive_code_token(match.group()):
                    symbols.add(match.group())
    return frozenset(symbols)


def internal_unbackticked_references(
    unit: InternalProseUnit, known: frozenset[str]
) -> list[str]:
    """Returns the distinct known names a prose unit uses without backticks."""
    text = _URI_PATTERN.sub(" ", InternalBACKTICK_SPAN_PATTERN.sub(" ", unit.text))
    if unit.kind == "entry":
        text = InternalENTRY_CAPTION_PATTERN.sub("", text)
    found: list[str] = []
    for match in InternalIDENTIFIER_PATTERN.finditer(text):
        name = match.group()
        if name not in known or name in found:
            continue
        if internal_reads_as_code_reference(name, text, match.start()):
            found.append(name)
    return found


_URI_PATTERN = re.compile("[a-zA-Z][a-zA-Z0-9+.-]*://\\S+")

InternalIDENTIFIER_PATTERN = re.compile("[A-Za-z_][A-Za-z0-9_]*")

InternalENTRY_CAPTION_PATTERN = re.compile("^\\S+(?:\\s*\\([^)]*\\))?:\\s*")
