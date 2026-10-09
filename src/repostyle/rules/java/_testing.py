"""Java test rules: naming, fakes, straight-line assertions, and no sleeps.

A Java test is a method a JUnit 5 test annotation marks, in a file the Java
layout places among the tests. Each rule holds such a test to the contract the
Python rule of the same id holds a pytest test to.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from repostyle.languages import (
    JAVA,
    JavaDeclaration,
    JavaToken,
    java_code_tokens,
    java_declarations,
    java_imports,
)
from repostyle.rules._violation import (
    RS_CONDITIONAL_TEST_LOGIC,
    RS_NO_MOCK_PATCH,
    RS_SLEEPY_TEST,
    RS_TEST_NAMING,
    Violation,
)


def check_java_test_naming(path: Path, source: str) -> Iterator[Violation]:
    """A Java test is named `stateUnderTest_expectedBehavior`.

    The house convention names a test for the state it sets up and the behavior
    it expects, as two lower-camel-case halves joined by one underscore
    (`emptyQueue_returnsNothing`), the Java spelling of the Python
    `test_StateUnderTest_ExpectedBehavior`.
    """
    for test in _test_methods(path, source):
        if _TEST_NAME_PATTERN.match(test.name) is None:
            yield Violation(
                test.line,
                test.column + 1,
                RS_TEST_NAMING,
                f"test '{test.name}' must match `stateUnderTest_expectedBehavior`",
            )


_TEST_NAME_PATTERN = re.compile(r"^[a-z][A-Za-z0-9]*_[a-z][A-Za-z0-9]*$")


def check_java_no_mock_library(path: Path, source: str) -> Iterator[Violation]:
    """Rejects a Java mock-library import; write a fake instead.

    Mockito, EasyMock, PowerMock, JMock, and MockK verify a unit by the calls
    it makes rather than the state it leaves, so a test written with one breaks
    under a refactor that keeps the behavior. A fake implementation of the
    collaborator's interface keeps the test asserting outcomes.
    """
    for imported in java_imports(source):
        root = next((r for r in _MOCK_ROOTS if _is_under(imported.name, r)), None)
        if root is not None:
            yield Violation(
                imported.line,
                imported.column + 1,
                RS_NO_MOCK_PATCH,
                f"`{root}` rejected; implement a fake of the collaborator's "
                f"interface instead",
            )


_MOCK_ROOTS = ("org.mockito", "org.easymock", "org.powermock", "org.jmock", "io.mockk")


def _is_under(name: str, root: str) -> bool:
    """Reports whether a dotted import name is `root` or lies beneath it."""
    return name == root or name.startswith(f"{root}.")


def check_java_conditional_test_logic(path: Path, source: str) -> Iterator[Violation]:
    """Rejects an assertion wrapped in a Java test's control flow.

    An `if`, `else`, loop, `switch`, `catch`, or `finally` block that calls an
    assertion (`assertEquals`, `assertThat`, `fail`, ...) among its own
    statements makes whether the test asserts depend on the path it takes. A
    `try` block counts only when a `catch` or `finally` follows it, since a
    bare try-with-resources only scopes a resource, as a Python `with` does.
    """
    code = java_code_tokens(source)
    for test in _test_methods(path, source):
        start, stop = test.body or (0, 0)
        for keyword, block in _control_blocks(code, start, stop):
            if _asserts_directly(code, block):
                yield Violation(
                    keyword.line,
                    keyword.column + 1,
                    RS_CONDITIONAL_TEST_LOGIC,
                    f"test '{test.name}' wraps an assertion in control flow; "
                    f"keep the asserted path straight-line",
                )


def check_java_sleepy_test(path: Path, source: str) -> Iterator[Violation]:
    """Rejects a nonzero real sleep in a Java test.

    `Thread.sleep(...)` and a `TimeUnit` constant's `sleep(...)` make a test
    slow and, where the sleep stands in for a condition, flaky; wait on the
    condition or advance a fake clock. A literal zero delay is left alone.
    """
    code = java_code_tokens(source)
    for test in _test_methods(path, source):
        start, stop = test.body or (0, 0)
        for index in range(start + 2, stop - 1):
            receiver = code[index - 2].text
            if (
                code[index].text == "sleep"
                and code[index - 1].text == "."
                and code[index + 1].text == "("
                and receiver in _SLEEP_RECEIVERS
                and not _is_zero_delay(code, index + 2)
            ):
                yield Violation(
                    code[index - 2].line,
                    code[index - 2].column + 1,
                    RS_SLEEPY_TEST,
                    f"`{receiver}.sleep(...)` in a test is slow and flaky; wait "
                    f"on a condition or use a fake clock",
                )


_SLEEP_RECEIVERS = frozenset(
    {
        "Thread",
        "NANOSECONDS",
        "MICROSECONDS",
        "MILLISECONDS",
        "SECONDS",
        "MINUTES",
        "HOURS",
        "DAYS",
    }
)


def _asserts_directly(code: tuple[JavaToken, ...], block: tuple[int, int]) -> bool:
    """Reports whether a block's own statements call an assertion.

    A call inside a nested block is that block's to report, so only calls at
    the block's own brace depth count.
    """
    depth = 0
    start, stop = block
    for index in range(start, stop):
        text = code[index].text
        if text == "{":
            depth += 1
        elif text == "}":
            depth -= 1
        elif depth == 0 and _is_assertion_call(code, index, stop):
            return True
    return False


def _is_zero_delay(code: tuple[JavaToken, ...], index: int) -> bool:
    """Reports whether the call arguments at `index` are a literal zero."""
    return (
        index + 1 < len(code)
        and code[index].text in {"0", "0L"}
        and code[index + 1].text == ")"
    )


def _test_methods(path: Path, source: str) -> Iterator[JavaDeclaration]:
    """Yields each JUnit test method in a Java test file."""
    if not JAVA.is_test_file(path):
        return
    for declaration in java_declarations(source):
        if declaration.kind == "method" and _TEST_ANNOTATIONS.intersection(
            declaration.annotations
        ):
            yield declaration


_TEST_ANNOTATIONS = frozenset(
    {"Test", "ParameterizedTest", "RepeatedTest", "TestFactory", "TestTemplate"}
)


_Span = tuple[int, int]


def _control_blocks(
    code: tuple[JavaToken, ...], start: int, stop: int
) -> Iterator[tuple[JavaToken, _Span]]:
    """Yields each conditional block in a method body and its keyword.

    A block is the `[start, stop)` token span a keyword controls: its braces'
    contents, or the single statement it governs without braces.
    """
    for index in range(start, stop):
        keyword = code[index]
        if keyword.kind != "ident" or keyword.text not in _CONTROL_KEYWORDS:
            continue
        block = _governed_block(code, index + 1, stop)
        if keyword.text == "try" and not _has_handler(code, block[1], stop):
            continue
        yield keyword, block


_CONTROL_KEYWORDS = frozenset(
    {"if", "else", "for", "while", "do", "switch", "try", "catch", "finally"}
)


def _governed_block(
    code: tuple[JavaToken, ...], index: int, stop: int
) -> tuple[int, int]:
    """Returns the span a control keyword at `index - 1` governs.

    A parenthesized condition, resource list, or catch parameter is stepped
    over first. Braces give the span their contents; otherwise the span runs
    through the next `;`.
    """
    if index < stop and code[index].text == "(":
        index = _closing(code, index, stop, "(", ")") + 1
    if index < stop and code[index].text == "{":
        return index + 1, _closing(code, index, stop, "{", "}")
    end = index
    while end < stop and code[end].text != ";":
        end += 1
    return index, end


def _closing(
    code: tuple[JavaToken, ...], index: int, stop: int, opener: str, closer: str
) -> int:
    """Returns the index of the `closer` matching the `opener` at `index`."""
    depth = 0
    for position in range(index, stop):
        if code[position].text == opener:
            depth += 1
        elif code[position].text == closer:
            depth -= 1
            if depth == 0:
                return position
    return stop


def _has_handler(code: tuple[JavaToken, ...], block_end: int, stop: int) -> bool:
    """Reports whether a `catch` or `finally` follows a `try` block's end."""
    following = block_end + 1
    return following < stop and code[following].text in {"catch", "finally"}


def _is_assertion_call(code: tuple[JavaToken, ...], index: int, stop: int) -> bool:
    """Reports whether the token at `index` names a called assertion."""
    token = code[index]
    return (
        token.kind == "ident"
        and (token.text.startswith("assert") or token.text == "fail")
        and index + 1 < stop
        and code[index + 1].text == "("
    )
