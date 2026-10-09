"""Java contract rules: durations, parameter counts, and Javadoc tags."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

from repostyle.languages import java_declarations
from repostyle.rules._doc_value_analysis import internal_describes_param_as_subject
from repostyle.rules._javadoc import InternalJavadoc, internal_javadoc
from repostyle.rules._violation import (
    RS_ARG_DESCRIBED_IN_PROSE,
    RS_DURATION_AS_TIMEDELTA,
    RS_RECORD_COMPONENT_UNDOCUMENTED,
    RS_TOO_MANY_POSITIONAL_ARGS,
    Violation,
)
from repostyle.rules.signatures import MAX_POSITIONAL_ARGS


def check_java_duration_constant(path: Path, source: str) -> Iterator[Violation]:
    """A Java duration constant is a `Duration`, not a raw number of units.

    Flags a `static final` field of a primitive or boxed numeric type whose
    name ends in a time unit (`_SECONDS`, `_MILLIS`, `_MS`, `_MINUTES`, ...). A
    `java.time.Duration` carries its unit with it, so a caller cannot read
    milliseconds as seconds, and converting it to the integer a library takes
    happens once, at that boundary, without overflow arithmetic by hand. A
    conversion factor named for one unit per another (`MILLIS_PER_SECOND`) does
    not end in a unit and is left alone.
    """
    for declaration in java_declarations(source):
        if declaration.kind != "field":
            continue
        if not {"static", "final"} <= declaration.modifiers:
            continue
        match = _DURATION_NAME_PATTERN.search(declaration.name)
        if match is None or declaration.type_text not in _NUMERIC_TYPES:
            continue
        factory = _DURATION_FACTORIES[match.group(1)]
        yield Violation(
            declaration.line,
            declaration.column + 1,
            RS_DURATION_AS_TIMEDELTA,
            f"'{declaration.name}' is a duration held as a raw "
            f"{declaration.type_text}; declare a `Duration` with "
            f"`Duration.{factory}(...)` instead",
        )


_DURATION_FACTORIES = {
    "SECONDS": "ofSeconds",
    "SECS": "ofSeconds",
    "MILLIS": "ofMillis",
    "MILLISECONDS": "ofMillis",
    "MS": "ofMillis",
    "NANOS": "ofNanos",
    "NANOSECONDS": "ofNanos",
    "MINUTES": "ofMinutes",
    "MINS": "ofMinutes",
    "HOURS": "ofHours",
    "DAYS": "ofDays",
}

_DURATION_NAME_PATTERN = re.compile(rf"_({'|'.join(_DURATION_FACTORIES)})$")

_NUMERIC_TYPES = frozenset(
    {"int", "long", "short", "double", "float", "Integer", "Long", "Double"}
)


def check_java_too_many_parameters(path: Path, source: str) -> Iterator[Violation]:
    """Flags a Java method or constructor over the parameter limit.

    Java has only positional parameters, so RS027's limit of five applies to
    every parameter a method or constructor declares. An `@Override` method is
    exempt, since its supertype fixes the signature, and so is a record, whose
    components are its fields. A call site past the limit reads as a row of
    unlabeled values; a parameter object or builder names them.
    """
    for declaration in java_declarations(source):
        if declaration.kind not in {"method", "constructor"}:
            continue
        if "Override" in declaration.annotations:
            continue
        count = len(declaration.parameters)
        if count <= MAX_POSITIONAL_ARGS:
            continue
        yield Violation(
            declaration.line,
            declaration.column + 1,
            RS_TOO_MANY_POSITIONAL_ARGS,
            f"{declaration.kind} '{declaration.name}' has {count} parameters; over "
            f"the limit of {MAX_POSITIONAL_ARGS}, group them into a parameter "
            f"object or builder",
        )


def check_java_param_described_in_prose(path: Path, source: str) -> Iterator[Violation]:
    """Flags a parameter explained in Javadoc prose, not in an `@param` tag.

    A method or constructor fires once per parameter that opens a sentence of
    its Javadoc summary or body as a `{@code}` subject while no `@param` tag
    documents it (`{@code sink} is invoked on the reader thread`). That detail
    belongs in `@param sink`, where the Javadoc tool and IDEs show it beside
    the parameter, and the summary states the member's own contract. A
    parameter merely referenced inside the contract prose does not fire, and
    neither does an undocumented parameter.
    """
    source_lines = source.splitlines()
    for declaration in java_declarations(source):
        if declaration.kind not in {"method", "constructor"} or declaration.doc is None:
            continue
        javadoc = internal_javadoc(declaration.doc, source_lines)
        documented = _tagged_names(javadoc, "@param")
        prose = " ".join(
            unit.text for unit in javadoc.units if unit.kind in {"summary", "body"}
        )
        for parameter in declaration.parameters:
            if parameter.name in documented:
                continue
            if not internal_describes_param_as_subject(prose, parameter.name):
                continue
            yield Violation(
                declaration.line,
                declaration.column + 1,
                RS_ARG_DESCRIBED_IN_PROSE,
                f"parameter '{parameter.name}' is described in the Javadoc prose "
                f"of '{declaration.name}'; move the description into an "
                f"`@param {parameter.name}` tag",
            )


def check_record_component_tags(path: Path, source: str) -> Iterator[Violation]:
    """A documented Java record gives each component an `@param` tag.

    A record component has no declaration of its own to carry a Javadoc
    comment, so the Javadoc tool reads its documentation from an `@param` tag
    in the record's comment and copies it onto the accessor and the canonical
    constructor. A record whose Javadoc leaves a component untagged ships that
    accessor undocumented. A record with no Javadoc at all is left to the rules
    that ask for documentation.
    """
    source_lines = source.splitlines()
    for declaration in java_declarations(source):
        if declaration.kind != "record" or declaration.doc is None:
            continue
        documented = _tagged_names(
            internal_javadoc(declaration.doc, source_lines), "@param"
        )
        for component in declaration.parameters:
            if component.name in documented:
                continue
            yield Violation(
                component.line,
                component.column + 1,
                RS_RECORD_COMPONENT_UNDOCUMENTED,
                f"record component '{component.name}' has no `@param` tag in "
                f"the Javadoc of '{declaration.name}'; document it there",
            )


def _tagged_names(javadoc: InternalJavadoc, tag: str) -> frozenset[str]:
    """Returns the names the `tag` block tags of a Javadoc comment document."""
    names: set[str] = set()
    for unit in javadoc.units:
        words = unit.text.split()
        if unit.kind == "tag" and len(words) > 1 and words[0] == tag:
            names.add(words[1])
    return frozenset(names)
