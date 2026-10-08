"""Brace and header walking over Java code tokens.

Each function takes the code tokens of one file -- comments other than Javadoc
already dropped -- and a `[start, stop)` range of indexes into them, so the
declaration scan composes them without re-lexing.
"""

from __future__ import annotations

from collections.abc import Iterator

from repostyle.languages._java import JavaToken


def member_header(
    code: list[JavaToken], start: int, stop: int
) -> tuple[list[JavaToken], int]:
    """Collects one member header, from `start` to its terminator.

    A header runs to the first `{`, `;`, or `=` outside parentheses.
    Parentheses nest, so an annotation argument (`@Foo(name = "x")`) never ends
    the header early.

    Returns:
        The header's tokens, and the terminator's index, or `stop` when the
        range ends first.
    """
    depth = 0
    for index in range(start, stop):
        text = code[index].text
        if depth == 0 and text in {"{", ";", "="}:
            return code[start:index], index
        depth += _PAREN_DEPTH.get(text, 0)
    return code[start:stop], stop


_PAREN_DEPTH = {"(": 1, ")": -1}


def matching_brace(code: list[JavaToken], opener: int, stop: int) -> int:
    """Returns the index of the `}` closing the `{` at `opener`."""
    depth = 0
    for index in range(opener, stop):
        depth += _BRACE_DEPTH.get(code[index].text, 0)
        if depth == 0:
            return index
    return stop


_BRACE_DEPTH = {"{": 1, "}": -1}


def statement_end(code: list[JavaToken], start: int, stop: int) -> int:
    """Returns the index of the first `;` outside any bracket from `start`.

    A field initializer and an enum's constant list both end there, however
    many lambdas, array initializers, or anonymous classes they hold.
    """
    depth = 0
    for index in range(start, stop):
        text = code[index].text
        if text == ";" and depth == 0:
            return index
        depth += _BRACKET_DEPTH.get(text, 0)
    return stop


_BRACKET_DEPTH = {"(": 1, "{": 1, "[": 1, ")": -1, "}": -1, "]": -1}


def split_annotations(
    tokens: list[JavaToken],
) -> tuple[tuple[str, ...], list[JavaToken]]:
    """Splits a header's annotations from its other tokens.

    The `@interface` keyword of an annotation type is not an annotation and
    stays with the other tokens.

    Returns:
        Each annotation's simple name, without `@`, package, or arguments, and
        the tokens left once every annotation is removed.
    """
    names: list[str] = []
    kept: list[JavaToken] = []
    index = 0
    while index < len(tokens):
        following = tokens[index + 1].text if index + 1 < len(tokens) else ""
        if tokens[index].text == "@" and following != "interface":
            index, name = _skip_annotation(tokens, index + 1)
            names.append(name)
            continue
        kept.append(tokens[index])
        index += 1
    return tuple(names), kept


def _skip_annotation(tokens: list[JavaToken], index: int) -> tuple[int, str]:
    """Steps over one annotation's dotted name and its argument list."""
    name = ""
    while index < len(tokens) and tokens[index].kind == "ident":
        name = tokens[index].text
        index += 1
        if index < len(tokens) and tokens[index].text == ".":
            index += 1
            continue
        break
    if index < len(tokens) and tokens[index].text == "(":
        depth = 0
        while index < len(tokens):
            depth += _PAREN_DEPTH.get(tokens[index].text, 0)
            index += 1
            if depth == 0:
                break
    return index, name


def parameter_segments(tokens: list[JavaToken]) -> Iterator[list[JavaToken]]:
    """Yields the comma-separated segments of a parameter list.

    The list ends at the `)` matching its opener. A comma inside generic angle
    brackets or nested parentheses does not separate parameters.

    Args:
        tokens: The tokens just past the list's opening `(`.
    """
    segment: list[JavaToken] = []
    depth = 0
    for token in tokens:
        if token.text in {")", ">"} and depth == 0:
            break
        depth += _GENERIC_DEPTH.get(token.text, 0)
        if token.text == "," and depth == 0:
            yield segment
            segment = []
            continue
        segment.append(token)
    yield segment


_GENERIC_DEPTH = {"(": 1, "<": 1, ")": -1, ">": -1}


def first_declarator(tokens: list[JavaToken]) -> int:
    """Returns the index of the name a field header declares first.

    `int a, b;` declares `a` first; a comma inside a generic type argument
    (`Map<String, Integer> m`) does not separate declarators.
    """
    depth = 0
    for index, token in enumerate(tokens):
        depth += _ANGLE_DEPTH.get(token.text, 0)
        if token.text == "," and depth == 0:
            return index - 1
    return len(tokens) - 1


_ANGLE_DEPTH = {"<": 1, ">": -1}


def joined_type(tokens: list[JavaToken]) -> str:
    """Joins type tokens, spacing only between two word tokens."""
    joined = ""
    for token in tokens:
        if joined and _is_word_edge(joined[-1]) and _is_word_edge(token.text[0]):
            joined += " "
        joined += token.text
    return joined


def _is_word_edge(character: str) -> bool:
    """Reports whether a character can end or start a word token."""
    return character.isalnum() or character in "_$"


def without_type_parameters(type_text: str) -> str:
    """Drops a method's leading `<T>` type-parameter list from its type."""
    if not type_text.startswith("<"):
        return type_text
    depth = 0
    for index, character in enumerate(type_text):
        depth += _ANGLE_DEPTH.get(character, 0)
        if depth == 0:
            return type_text[index + 1 :].strip()
    return type_text
