"""Cognitive complexity of a Java method body, scored from its tokens.

The score follows the cognitive-complexity rules RS012 applies to Python. Each
break in linear flow -- an `if`, `else`, loop, `switch`, `catch`, or ternary --
costs one, plus one per level of nesting it sits at, though an `else` or
`else if` costs one flat. Each run of like boolean operators costs one. A
lambda body nests what it holds without costing anything itself.
"""

from __future__ import annotations

from repostyle.languages import JavaToken


def java_cognitive_complexity(
    code: tuple[JavaToken, ...], body: tuple[int, int]
) -> int:
    """Returns the cognitive complexity of the method body spanning `body`.

    Args:
        code: The file's code tokens, as `java_code_tokens` returns them.
        body: The `[start, stop)` token span between the body's braces.
    """
    start, stop = body
    nesting_braces = _nesting_braces(code, start, stop)
    score = 0
    nesting = 0
    opened: list[bool] = []
    previous_operator = ""
    for index in range(start, stop):
        token = code[index]
        score += _structure_cost(code, index, nesting)
        operator = _boolean_operator(code, index)
        if operator:
            score += int(operator != previous_operator)
            previous_operator = operator
        elif token.text in _OPERATOR_RESETS:
            previous_operator = ""
        if token.text == "{":
            is_nesting = index in nesting_braces
            opened.append(is_nesting)
            nesting += int(is_nesting)
        elif token.text == "}" and opened:
            nesting -= int(opened.pop())
    return score


_OPERATOR_RESETS = frozenset({";", "{", "}", "(", ")", ","})


def _structure_cost(code: tuple[JavaToken, ...], index: int, nesting: int) -> int:
    """Returns what the token at `index` adds as a flow-breaking structure."""
    token = code[index]
    previous = code[index - 1].text if index else ""
    following = code[index + 1].text if index + 1 < len(code) else ""
    if token.kind == "ident" and token.text in _NESTED_STRUCTURES:
        if token.text == "if" and previous == "else":
            return 1
        if token.text == "while" and previous == "}" and _ends_do_loop(code, index):
            return 0
        return 1 + nesting
    if token.text == "else" and following != "if":
        return 1
    if token.text == "?" and _is_ternary(previous, following):
        return 1 + nesting
    return 0


_NESTED_STRUCTURES = frozenset({"if", "for", "while", "do", "switch", "catch"})


def _ends_do_loop(code: tuple[JavaToken, ...], index: int) -> bool:
    """Reports whether the `while` at `index` closes a `do` loop.

    A `do` loop's `while (...)` condition ends in `;`, where a `while` loop's
    opens its body. The `do` already paid for the loop, so its tail is free.
    """
    depth = 0
    for position in range(index + 1, len(code)):
        depth += {"(": 1, ")": -1}.get(code[position].text, 0)
        if depth == 0:
            following = position + 1
            return following < len(code) and code[following].text == ";"
    return False


def _is_ternary(previous: str, following: str) -> bool:
    """Reports whether a `?` is a conditional operator, not a type wildcard."""
    return previous not in {"<", ","} and following not in _WILDCARD_FOLLOWERS


_WILDCARD_FOLLOWERS = frozenset({"extends", "super", ">", ","})


def _boolean_operator(code: tuple[JavaToken, ...], index: int) -> str:
    """Returns `&&` or `||` when the token at `index` opens one, else empty.

    The lexer splits each operator into two adjacent one-character tokens.
    """
    token = code[index]
    if token.text not in {"&", "|"} or index + 1 >= len(code):
        return ""
    following = code[index + 1]
    is_adjacent = following.line == token.line and following.column == token.column + 1
    is_pair = following.text == token.text and is_adjacent
    is_second_half = index > 0 and code[index - 1].text == token.text
    if is_pair and not is_second_half:
        return token.text * 2
    return ""


def _nesting_braces(code: tuple[JavaToken, ...], start: int, stop: int) -> set[int]:
    """Returns the indexes of the `{` tokens that open a nesting level.

    A structure's braces nest -- an `if`, `else`, loop, `switch`, or `catch`
    block, and a lambda body -- while a `try` or `finally` block, a `case ->`
    rule body, an anonymous class body, and an array initializer do not, as
    none of them costs a reader a branch.
    """
    braces: set[int] = set()
    for index in range(start, stop):
        text = code[index].text
        if text in _BLOCK_OPENERS and code[index].kind == "ident":
            brace = _block_brace(code, index + 1, stop)
            if brace is not None:
                braces.add(brace)
        elif _opens_lambda_block(code, index, stop):
            braces.add(index + 2)
    return braces


_BLOCK_OPENERS = frozenset({"if", "else", "for", "while", "do", "switch", "catch"})


def _block_brace(code: tuple[JavaToken, ...], index: int, stop: int) -> int | None:
    """Returns the `{` a structure keyword opens, past its header."""
    if index < stop and code[index].text == "(":
        depth = 0
        while index < stop:
            depth += {"(": 1, ")": -1}.get(code[index].text, 0)
            index += 1
            if depth == 0:
                break
    if index < stop and code[index].text == "{":
        return index
    return None


def _opens_lambda_block(code: tuple[JavaToken, ...], index: int, stop: int) -> bool:
    """Reports whether a `-> {` at `index` opens a lambda body.

    A switch rule writes the same arrow after its `case` or `default` label, so
    an arrow whose statement opened with one of those is not a lambda.
    """
    if index + 2 >= stop or code[index].text != "-" or code[index + 1].text != ">":
        return False
    if code[index + 2].text != "{":
        return False
    for position in range(index - 1, -1, -1):
        text = code[position].text
        if text in {"case", "default"}:
            return False
        if text in {";", "{", "}"}:
            return True
    return True
