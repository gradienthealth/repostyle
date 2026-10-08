"""Java declarations: the types and members a source file introduces.

The scan reads the lexer's tokens with a brace stack, so it knows whether each
`{` opens a type body, whose members are declarations, or a code body, which it
steps over. It reads headers -- modifiers, annotations, a name, a parameter
list -- and never expressions, so a local variable or an anonymous class inside
a method body is not a declaration here.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from typing import NamedTuple

from repostyle.languages._java import JavaToken, lex_java
from repostyle.languages._java_headers import (
    first_declarator,
    joined_type,
    matching_brace,
    member_header,
    parameter_segments,
    split_annotations,
    statement_end,
    without_type_parameters,
)


class JavaParameter(NamedTuple):
    type_text: str
    """The declared type, annotations and `final` dropped (`List<String>`)."""
    name: str
    """The parameter or record component name."""
    line: int
    """1-based line the name sits on."""
    column: int
    """0-based column of the name."""


class JavaDeclaration(NamedTuple):
    kind: str
    """`class`, `interface`, `enum`, `record`, `annotation`, `method`,
    `constructor`, or `field`."""
    name: str
    """The declared name."""
    line: int
    """1-based line the name sits on."""
    column: int
    """0-based column of the name."""
    modifiers: frozenset[str]
    """The modifier keywords written on the declaration."""
    annotations: tuple[str, ...]
    """Each annotation's simple name, without its `@` or arguments."""
    type_text: str
    """A field's type or a method's return type; empty otherwise."""
    parameters: tuple[JavaParameter, ...]
    """A method's or constructor's parameters, or a record's components."""
    doc: JavaToken | None
    """The Javadoc comment directly above the declaration, if any."""
    owner: str
    """The enclosing type's name, empty for a top-level type."""
    body: tuple[int, int] | None
    """The `[start, stop)` indexes into `java_code_tokens` between the braces
    of a method's, constructor's, or type's body, or `None` without one."""


@lru_cache(maxsize=128)
def java_declarations(source: str) -> tuple[JavaDeclaration, ...]:
    """Returns every type and member declaration in Java `source`.

    A member of a nested type is returned with that type as its owner. An
    enum's constants, an initializer block, and anything inside a method body
    are not declarations. A header the scan cannot classify is skipped rather
    than guessed at.

    Returns:
        Each declaration in source order.
    """
    code = list(java_code_tokens(source))
    return tuple(_body_declarations(code, 0, len(code), "", "unit"))


@lru_cache(maxsize=128)
def java_code_tokens(source: str) -> tuple[JavaToken, ...]:
    """Returns the tokens of Java `source` that are code or Javadoc.

    Line and block comments are dropped, so an index the declaration scan
    reports addresses this tuple.
    """
    return tuple(t for t in lex_java(source) if t.kind not in _PLAIN_COMMENTS)


_PLAIN_COMMENTS = frozenset({"line_comment", "block_comment"})


def _body_declarations(
    code: list[JavaToken], start: int, stop: int, owner: str, owner_kind: str
) -> Iterator[JavaDeclaration]:
    """Yields the declarations in one type body or the compilation unit.

    `start` and `stop` bound the body between its braces. An enum body's
    constants run to its first top-level `;` and are skipped, and a member's
    own body -- a method's code or a field's initializer -- is stepped over,
    except that a nested type's body is scanned for its own members.
    """
    if owner_kind == "enum":
        start = statement_end(code, start, stop) + 1
    while start < stop:
        header, end = member_header(code, start, stop)
        body, member_end = _member_extent(code, end, stop)
        declaration = _declaration(header, owner, owner_kind, body)
        if declaration is not None:
            yield declaration
            if declaration.kind in TYPE_KINDS and body is not None:
                yield from _body_declarations(
                    code, body[0], body[1], declaration.name, declaration.kind
                )
        start = member_end + 1


def _member_extent(
    code: list[JavaToken], end: int, stop: int
) -> tuple[tuple[int, int] | None, int]:
    """Locates the body a member header's terminator opens, and its end.

    A `{` opens a body that runs to its matching `}`; an `=` opens a field
    initializer that runs to its `;`; a `;` ends the member where it stands.

    Returns:
        The body's `[start, stop)` span, `None` for a member without one, and
        the index of the member's last token.
    """
    terminator = code[end].text if end < stop else ";"
    if terminator == "{":
        closing = matching_brace(code, end, stop)
        return (end + 1, closing), closing
    if terminator == "=":
        return None, statement_end(code, end, stop)
    return None, end


TYPE_KINDS = frozenset({"class", "interface", "enum", "record", "annotation"})


_MODIFIERS = frozenset(
    {
        "public",
        "protected",
        "private",
        "static",
        "final",
        "abstract",
        "default",
        "synchronized",
        "native",
        "transient",
        "volatile",
        "strictfp",
        "sealed",
        "non-sealed",
    }
)


def _declaration(
    header: list[JavaToken],
    owner: str,
    owner_kind: str,
    body: tuple[int, int] | None,
) -> JavaDeclaration | None:
    """Builds the declaration one member header introduces, or `None`.

    A package or import statement, an initializer block, and a compact
    canonical constructor introduce no declaration.
    """
    doc = header[0] if header and header[0].kind == "doc_comment" else None
    annotations, rest = split_annotations(header[1:] if doc else header)
    modifiers = frozenset(t.text for t in rest if t.text in _MODIFIERS)
    rest = [t for t in rest if t.text not in _MODIFIERS]
    if not rest:
        return None
    texts = [t.text for t in rest]
    partial = _Partial(modifiers, annotations, doc, owner, body)
    if texts[0] in _TYPE_KEYWORDS or texts[:2] == ["@", "interface"]:
        return _type_declaration(rest, partial)
    if owner_kind == "unit":
        return None
    if "(" in texts:
        return _callable_declaration(rest, texts.index("("), partial)
    return _field_declaration(rest, partial)


_TYPE_KEYWORDS = frozenset({"class", "interface", "enum", "record"})


class _Partial(NamedTuple):
    modifiers: frozenset[str]
    """The header's modifier keywords."""
    annotations: tuple[str, ...]
    """The header's annotation names."""
    doc: JavaToken | None
    """The header's leading Javadoc."""
    owner: str
    """The enclosing type's name."""
    body: tuple[int, int] | None
    """The token span of the body a `{` ending the header opens."""


def _callable_declaration(
    rest: list[JavaToken], paren: int, partial: _Partial
) -> JavaDeclaration | None:
    """Builds a method or constructor from the header's tokens."""
    if paren == 0 or rest[paren - 1].kind != "ident":
        return None
    name = rest[paren - 1]
    type_text = without_type_parameters(joined_type(rest[: paren - 1]))
    is_constructor = not type_text and name.text == partial.owner
    kind = "constructor" if is_constructor else "method"
    return _build(kind, name, type_text, _parameters(rest[paren + 1 :]), partial)


def _field_declaration(
    rest: list[JavaToken], partial: _Partial
) -> JavaDeclaration | None:
    """Builds a field from the header's tokens, naming its first declarator."""
    index = first_declarator(rest)
    if index <= 0 or rest[index].kind != "ident":
        return None
    return _build("field", rest[index], joined_type(rest[:index]), (), partial)


def _type_declaration(
    rest: list[JavaToken], partial: _Partial
) -> JavaDeclaration | None:
    """Builds a class, interface, enum, record, or annotation type."""
    is_annotation = rest[0].text == "@"
    keyword = 1 if is_annotation else 0
    if keyword + 1 >= len(rest):
        return None
    name = rest[keyword + 1]
    texts = [t.text for t in rest]
    parameters: tuple[JavaParameter, ...] = ()
    if rest[keyword].text == "record" and "(" in texts:
        parameters = _parameters(rest[texts.index("(") + 1 :])
    kind = "annotation" if is_annotation else rest[keyword].text
    return _build(kind, name, "", parameters, partial)


def _build(
    kind: str,
    name: JavaToken,
    type_text: str,
    parameters: tuple[JavaParameter, ...],
    partial: _Partial,
) -> JavaDeclaration:
    """Assembles a declaration from its parts and its header's fields."""
    return JavaDeclaration(
        kind,
        name.text,
        name.line,
        name.column,
        partial.modifiers,
        partial.annotations,
        type_text,
        parameters,
        partial.doc,
        partial.owner,
        body=partial.body,
    )


def _parameters(tokens: list[JavaToken]) -> tuple[JavaParameter, ...]:
    """Parses the parameter list whose tokens start past its `(`."""
    parameters: list[JavaParameter] = []
    for segment in parameter_segments(tokens):
        _, kept = split_annotations(segment)
        kept = [token for token in kept if token.text != "final"]
        if len(kept) < 2 or kept[-1].kind != "ident":
            continue
        name = kept[-1]
        parameters.append(
            JavaParameter(joined_type(kept[:-1]), name.text, name.line, name.column)
        )
    return tuple(parameters)
