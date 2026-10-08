"""Java naming rules: acronyms as words, spelled-out words, honest types.

Each rule shares its vocabulary with the Python rule of the same id -- the
banned abbreviations, the vague class suffixes -- and applies it under Java's
own naming convention, where Google Java style writes an acronym as a word.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from repostyle.languages import JavaDeclaration, java_declarations
from repostyle.rules._violation import (
    RS_ACRONYM_CASING,
    RS_BANNED_ABBREVIATION,
    RS_DISCOURAGED_CLASS_SUFFIX,
    Violation,
)
from repostyle.rules.naming_abbreviations import (
    BANNED_ABBREVIATIONS,
    identifier_words,
)
from repostyle.rules.naming_special import DISCOURAGED_CLASS_SUFFIXES


def check_java_acronym_as_word(path: Path, source: str) -> Iterator[Violation]:
    """A Java name writes an acronym as a word: `DicomScp`, not `DICOMScp`.

    Google Java style converts a name to camel case word by word, so an acronym
    takes one capital like any other word (`XmlHttpRequest`, `customerId`,
    `supportsIpv6OnIos`). The check fires wherever two or more capitals stand
    together as one word -- before the next word's capital (`IOException`), at
    the end of a name or underscore-separated segment (`remoteAE`), or before a
    digit -- in a declared type, method, field, parameter, or record component.
    A lone capital before the next word (`getAValue`) is a one-letter word and
    is left alone. A constant (`UPPER_SNAKE`), an `@Override` method, whose
    name is fixed by its supertype, and the `IT` suffix of an integration-test
    class are exempt.
    """
    for name, line, column in _introduced_names(source):
        for run, word in _acronym_runs(name):
            yield Violation(
                line,
                column + 1,
                RS_ACRONYM_CASING,
                f"'{name}' writes the acronym '{run}' in capitals; Google Java "
                f"style writes it as a word, '{word}'",
            )


def check_java_banned_abbreviation(path: Path, source: str) -> Iterator[Violation]:
    """Flags a declared Java name that drops letters from a known word.

    The vocabulary is RS010's (`cfg`, `ctx`, `req`, `resp`, `conn`, ...). A
    declared type, method, field, parameter, or record component name is split
    into its camel-case and underscore words, and a word equal to a banned
    abbreviation is rejected in favor of the spelled-out word. An `@Override`
    method is exempt, since its supertype spells its name.
    """
    for name, line, column in _introduced_names(source):
        for word in identifier_words(name):
            if word in BANNED_ABBREVIATIONS:
                yield Violation(
                    line,
                    column + 1,
                    RS_BANNED_ABBREVIATION,
                    f"'{name}' uses the abbreviation '{word}'; spell the word out",
                )


def check_java_discouraged_class_suffix(path: Path, source: str) -> Iterator[Violation]:
    """Flags a Java type named for a vague agent role.

    `Manager`, `Helper`, `Util`, and `Utils` name what a type loosely does
    rather than what it is, and tend to accrete unrelated procedures; name the
    responsibility instead (`ConnectionPool`, not `ConnectionManager`). Every
    class, interface, enum, and record is checked.
    """
    for declaration in java_declarations(source):
        if declaration.kind not in _TYPE_KINDS:
            continue
        suffix = next(
            (s for s in DISCOURAGED_CLASS_SUFFIXES if declaration.name.endswith(s)),
            None,
        )
        if suffix is not None:
            yield Violation(
                declaration.line,
                declaration.column + 1,
                RS_DISCOURAGED_CLASS_SUFFIX,
                f"class '{declaration.name}' ends in '{suffix}'; name the "
                f"responsibility, not a vague agent role",
            )


_TYPE_KINDS = frozenset({"class", "interface", "enum", "record", "annotation"})


def _introduced_names(source: str) -> Iterator[tuple[str, int, int]]:
    """Yields `(name, line, column)` for each name the source introduces.

    A name the file does not choose is skipped: an `@Override` method's name
    and parameters, a constructor's name, which is its class's, and a constant.
    """
    for declaration in java_declarations(source):
        if "Override" in declaration.annotations:
            continue
        if declaration.kind != "constructor" and not _is_constant(declaration):
            yield declaration.name, declaration.line, declaration.column
        for parameter in declaration.parameters:
            yield parameter.name, parameter.line, parameter.column


def _is_constant(declaration: JavaDeclaration) -> bool:
    """Reports whether a field is an `UPPER_SNAKE` constant."""
    return (
        declaration.kind == "field"
        and _CONSTANT_PATTERN.match(declaration.name) is not None
    )


_CONSTANT_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _acronym_runs(name: str) -> Iterator[tuple[str, str]]:
    """Yields `(run, word)` for each all-capitals acronym run in `name`.

    The run is the acronym as written and the word its camel-case spelling. A
    capitals run followed by a lowercase letter loses its last capital to the
    next word (`DICOMScp` runs `DICOM`, then `Scp`).
    """
    if name.endswith("IT") and name[:-2][-1:].islower():
        name = name[:-2]
    for segment in name.split("_"):
        for match in _CAPITALS_PATTERN.finditer(segment):
            run = match.group()
            followed_by_lowercase = segment[match.end() : match.end() + 1].islower()
            if followed_by_lowercase:
                run = run[:-1]
            if len(run) >= 2:
                yield run, run[0] + run[1:].lower()


_CAPITALS_PATTERN = re.compile(r"[A-Z]{2,}")
