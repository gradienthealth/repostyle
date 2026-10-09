"""Java assertion library rule: every test asserts with one library."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from repostyle._shared import _repostyle_table, find_config_file
from repostyle.languages import JAVA, JavaImport, java_code_tokens, java_imports
from repostyle.rules._violation import RS_ASSERTION_LIBRARY, Violation


def check_java_assertion_library(path: Path, source: str) -> Iterator[Violation]:
    """A Java test asserts with the repository's one assertion library.

    The library is `assertion-library` in the repostyle config: `truth` (the
    default), `assertj`, or `junit`. A test file importing another library's
    assertions -- Truth, AssertJ, Hamcrest, JUnit 4's `Assert`, or JUnit 5's
    `Assertions` -- is flagged, as is a call through an imported `Assertions`
    class. JUnit's `assertThrows`, `assertDoesNotThrow`, `assertTimeout`, and
    `fail` stay available whatever the choice, since Truth and AssertJ users
    reach for them too.

    Truth is the default because its `assertThat(actual).isEqualTo(expected)`
    names the value under test first, where `assertEquals(expected, actual)`
    invites swapping the two, and its failure messages describe collections,
    strings, and optionals rather than printing two values.
    """
    if not JAVA.is_test_file(path):
        return
    chosen = _chosen_library(path)
    for imported in java_imports(source):
        library = _foreign_library(imported, chosen)
        if library is not None:
            yield _violation(imported.line, imported.column, library, chosen)
    if not _imports_assertions_class(source) or chosen == "junit":
        return
    code = java_code_tokens(source)
    for index in range(len(code) - 2):
        if code[index].text == "Assertions" and code[index + 1].text == ".":
            member = code[index + 2].text
            if member not in _COMPANIONS:
                token = code[index]
                yield _violation(token.line, token.column, "junit", chosen)


def _violation(line: int, column: int, library: str, chosen: str) -> Violation:
    """Builds the finding for an assertion drawn from `library`."""
    return Violation(
        line,
        column + 1,
        RS_ASSERTION_LIBRARY,
        f"this test asserts with `{library}`, but the repository's "
        f"`assertion-library` is `{chosen}`",
    )


_LIBRARY_ROOTS = {
    "truth": "com.google.common.truth",
    "assertj": "org.assertj",
    "junit": "org.junit.jupiter.api.Assertions",
    "junit4": "org.junit.Assert",
    "hamcrest": "org.hamcrest",
}


_COMPANIONS = frozenset(
    {
        "assertDoesNotThrow",
        "assertThrows",
        "assertThrowsExactly",
        "assertTimeout",
        "assertTimeoutPreemptively",
        "fail",
    }
)


def _chosen_library(path: Path) -> str:
    """Returns the configured library, `truth` when unset."""
    configured = _repostyle_table(find_config_file(path)).get("assertion-library")
    return configured if configured in ASSERTION_LIBRARIES else "truth"


# The values `assertion-library` accepts; the runner refuses any other
ASSERTION_LIBRARIES = frozenset({"truth", "assertj", "junit"})


def _foreign_library(imported: JavaImport, chosen: str) -> str | None:
    """Returns the library an import draws assertions from, unless allowed.

    An import of a JUnit companion member, and a plain import of the
    `Assertions` class itself, whose calls are checked one by one, are allowed
    whatever the choice.
    """
    for library, root in _LIBRARY_ROOTS.items():
        if library == chosen:
            continue
        if imported.name != root and not imported.name.startswith(f"{root}."):
            continue
        if library == "junit" and _is_companion_or_class(imported):
            return None
        return library
    return None


def _imports_assertions_class(source: str) -> bool:
    """Reports whether `source` imports JUnit's `Assertions` class itself."""
    return any(
        not imported.is_static and imported.name == _LIBRARY_ROOTS["junit"]
        for imported in java_imports(source)
    )


def _is_companion_or_class(imported: JavaImport) -> bool:
    """Reports whether a JUnit `Assertions` import stays allowed."""
    member = imported.name.rsplit(".", 1)[-1]
    if not imported.is_static:
        return member == "Assertions"
    return member in _COMPANIONS
