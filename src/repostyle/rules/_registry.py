"""The rule registry mapping ids to check functions, plus `run_rule`."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from pathlib import Path

from repostyle.languages import language_for
from repostyle.rules._documentation_rules import RULES as DOCUMENTATION_RULES
from repostyle.rules._python_rules import RULES as PYTHON_RULES
from repostyle.rules._testing_rules import RULES as TESTING_RULES
from repostyle.rules._violation import (
    RS_ACRONYM_CASING_IN_PROSE,
    RS_ARG_DESCRIBED_IN_PROSE,
    RS_BANNER_COMMENT,
    RS_BEHAVIOR_VERIFICATION_ONLY,
    RS_BOOLEAN_PREFIX_REQUIRED,
    RS_BULLET_ITEM_CASING,
    RS_COGNITIVE_COMPLEXITY,
    RS_DEEPLY_NESTED_TYPE,
    RS_DISFAVORED_GCP_TERM,
    RS_DOC_FILL,
    RS_DOC_SUMMARY_OVERFLOW,
    RS_DOC_VALUE_SIGNAL,
    RS_DOCSTRING_SECTION_ALIAS,
    RS_DOCSTRING_SECTION_ORDER,
    RS_DOUBLE_SPACE_AFTER_PERIOD,
    RS_DUPLICATE_DOCSTRING_SECTION,
    RS_ELEMENT_ORDER,
    RS_EMPTY_CATCH_REASON,
    RS_EXCESSIVE_MOCKING,
    RS_FIELD_COMMENT_AS_DOCSTRING,
    RS_FIELD_DESCRIBED_IN_CLASS_DOCSTRING,
    RS_FILE_LITERAL_RESTATEMENT,
    RS_FILENAME_CONVENTION,
    RS_GCP_BARE_IDENTIFIER,
    RS_GLUED_CODE_SPAN,
    RS_IMPERATIVE_DOCSTRING_OPENING,
    RS_INVALID_DOCSTRING_SECTION,
    RS_LOWERCASE_ENTRY_DESCRIPTION,
    RS_NO_DOUBLE_BACKTICKS,
    RS_NO_NEGATED_BOOLEAN,
    RS_NONSTANDARD_DASH,
    RS_OVER_BROAD_EXCEPT,
    RS_PREDICATE_FUNCTION_NAMING,
    RS_PRIVATE_IMPORT,
    RS_RAISE_DESCRIBED_IN_PROSE,
    RS_RAISES_SECTION_INCOMPLETE,
    RS_RANGE_LEN_REINDEX,
    RS_RECORD_COMPONENT_UNDOCUMENTED,
    RS_REPEATED_TEST_SETUP,
    RS_RETURN_DESCRIBED_IN_PROSE,
    RS_SHARED_TEST_HELPER,
    RS_SHOULD_BE_PRIVATE,
    RS_SOURCE_MODULE_SIZE,
    RS_SUMMARY_COMMENT_AS_DOCSTRING,
    RS_TAG_COMMENT_CONTINUATION_INDENT,
    RS_TEMPORAL_MARKER,
    RS_TERMINAL_PUNCTUATION,
    RS_TEST_MODULE_SIZE,
    RS_TEST_PARAMETRIZATION_CANDIDATE,
    RS_TOO_MANY_POSITIONAL_ARGS,
    RS_UNBACKTICKED_CODE_REFERENCE,
    RS_UNBACKTICKED_SIBLING_SYMBOL,
    Severity,
    Violation,
)
from repostyle.rules.java import RULES as JAVA_RULES
from repostyle.rules.testing_reuse import (
    check_shared_test_helper,
)
from repostyle.rules.visibility import check_should_be_private

# The single-file check contract every RULES entry holds: a `(path, source)`
# pair in, a stream of violations out.
RuleCheck = Callable[[Path, str], Iterator[Violation]]

# A package rule sees every first-party file at once and yields its findings
# keyed by path, rather than the single-file `RuleCheck` contract above.
PackageCheck = Callable[[Sequence[tuple[Path, str]]], Iterator[tuple[Path, Violation]]]

RULES: RuleTable = {
    **PYTHON_RULES,
    **DOCUMENTATION_RULES,
    **TESTING_RULES,
}

# Checks bound to one language, keyed by its `Language.name`. The runner hands
# each only that language's files, so a check here reads its syntax without a
# guard of its own; the checks in RULES see every file and guard themselves.
RuleTable = dict[str, tuple[RuleCheck, ...]]

LANGUAGE_RULES: dict[str, RuleTable] = {
    "java": JAVA_RULES,
}


# Whole-package rules, run once over every first-party file rather than per
# file. Kept separate from RULES so the single-file contract is unchanged; the
# runner dispatches each through `run_package_rule`.
PACKAGE_RULES: dict[str, tuple[PackageCheck, ...]] = {
    RS_SHOULD_BE_PRIVATE: (check_should_be_private,),
    RS_SHARED_TEST_HELPER: (check_shared_test_helper,),
}


# An advisory rule -- a threshold, a judgment call, or a newer mechanical check
# still proving out its false-positive rate -- registers Severity.WARNING here
# to emit a non-blocking signal; the settled, low-false-positive rules stay at
# the default ERROR and fail the run.
RULE_SEVERITY: dict[str, Severity] = {
    RS_COGNITIVE_COMPLEXITY: Severity.WARNING,
    RS_EXCESSIVE_MOCKING: Severity.WARNING,
    RS_BEHAVIOR_VERIFICATION_ONLY: Severity.WARNING,
    RS_FILE_LITERAL_RESTATEMENT: Severity.WARNING,
    RS_TEST_MODULE_SIZE: Severity.WARNING,
    RS_SHARED_TEST_HELPER: Severity.WARNING,
    RS_TEST_PARAMETRIZATION_CANDIDATE: Severity.WARNING,
    RS_REPEATED_TEST_SETUP: Severity.WARNING,
    RS_SOURCE_MODULE_SIZE: Severity.WARNING,
    RS_DOC_VALUE_SIGNAL: Severity.WARNING,
    RS_ELEMENT_ORDER: Severity.WARNING,
    RS_SUMMARY_COMMENT_AS_DOCSTRING: Severity.WARNING,
    RS_FIELD_COMMENT_AS_DOCSTRING: Severity.WARNING,
    RS_NO_NEGATED_BOOLEAN: Severity.WARNING,
    RS_BOOLEAN_PREFIX_REQUIRED: Severity.WARNING,
    RS_TOO_MANY_POSITIONAL_ARGS: Severity.WARNING,
    RS_SHOULD_BE_PRIVATE: Severity.WARNING,
    RS_TERMINAL_PUNCTUATION: Severity.WARNING,
    RS_ARG_DESCRIBED_IN_PROSE: Severity.WARNING,
    RS_FIELD_DESCRIBED_IN_CLASS_DOCSTRING: Severity.WARNING,
    RS_RETURN_DESCRIBED_IN_PROSE: Severity.WARNING,
    RS_FILENAME_CONVENTION: Severity.WARNING,
    RS_IMPERATIVE_DOCSTRING_OPENING: Severity.WARNING,
    RS_DOC_SUMMARY_OVERFLOW: Severity.WARNING,
    RS_UNBACKTICKED_CODE_REFERENCE: Severity.WARNING,
    RS_GLUED_CODE_SPAN: Severity.WARNING,
    RS_TAG_COMMENT_CONTINUATION_INDENT: Severity.WARNING,
    RS_UNBACKTICKED_SIBLING_SYMBOL: Severity.WARNING,
    RS_DEEPLY_NESTED_TYPE: Severity.WARNING,
    RS_RAISE_DESCRIBED_IN_PROSE: Severity.WARNING,
    RS_RAISES_SECTION_INCOMPLETE: Severity.WARNING,
    RS_PREDICATE_FUNCTION_NAMING: Severity.WARNING,
    RS_TEMPORAL_MARKER: Severity.WARNING,
    RS_RANGE_LEN_REINDEX: Severity.WARNING,
    RS_LOWERCASE_ENTRY_DESCRIPTION: Severity.WARNING,
    RS_PRIVATE_IMPORT: Severity.WARNING,
    RS_ACRONYM_CASING_IN_PROSE: Severity.WARNING,
    RS_DISFAVORED_GCP_TERM: Severity.WARNING,
    RS_GCP_BARE_IDENTIFIER: Severity.WARNING,
    RS_OVER_BROAD_EXCEPT: Severity.WARNING,
    RS_BULLET_ITEM_CASING: Severity.WARNING,
    RS_NONSTANDARD_DASH: Severity.WARNING,
    RS_BANNER_COMMENT: Severity.WARNING,
    RS_INVALID_DOCSTRING_SECTION: Severity.WARNING,
    RS_DOCSTRING_SECTION_ORDER: Severity.WARNING,
    RS_DOCSTRING_SECTION_ALIAS: Severity.WARNING,
    RS_DUPLICATE_DOCSTRING_SECTION: Severity.WARNING,
    RS_DOUBLE_SPACE_AFTER_PERIOD: Severity.WARNING,
    RS_RECORD_COMPONENT_UNDOCUMENTED: Severity.WARNING,
    RS_EMPTY_CATCH_REASON: Severity.WARNING,
}


# The rules `repostyle --fix` rewrites in place. The single source both the
# runner's fix path and the `explain` card's fixable line consult, so a card
# never promises a fix the runner does not perform.
FIXABLE_RULES: frozenset[str] = frozenset(
    {
        RS_ACRONYM_CASING_IN_PROSE,
        RS_DISFAVORED_GCP_TERM,
        RS_DOC_FILL,
        RS_DOCSTRING_SECTION_ALIAS,
        RS_DOUBLE_SPACE_AFTER_PERIOD,
        RS_NO_DOUBLE_BACKTICKS,
        RS_NONSTANDARD_DASH,
        RS_TERMINAL_PUNCTUATION,
    }
)


def severity_of(rule_id: str) -> Severity:
    """Returns a rule's severity, defaulting to `ERROR`."""
    return RULE_SEVERITY.get(rule_id, Severity.ERROR)


def run_rule(rule_id: str, path: Path, source: str) -> Iterator[Violation]:
    """Runs a single rule by id over one source, yielding its violations.

    A rule id maps to shared checks, which see every file and guard themselves,
    and to the checks `LANGUAGE_RULES` binds to the file's language, which see
    only that language's files. RS005, for one, runs both a markdown and a
    Python-docstring backtick check, and RS001 adds a Java check for a Java
    file.
    """
    for check in RULES.get(rule_id, ()):
        yield from check(path, source)
    language = language_for(path)
    if language is None:
        return
    for check in LANGUAGE_RULES.get(language.name, {}).get(rule_id, ()):
        yield from check(path, source)


def run_package_rule(
    rule_id: str, files: Sequence[tuple[Path, str]]
) -> Iterator[tuple[Path, Violation]]:
    """Runs a whole-package rule by id over every first-party file."""
    for check in PACKAGE_RULES.get(rule_id, ()):
        yield from check(files)


ALL_RULE_IDS: frozenset[str] = (
    frozenset(RULES)
    | frozenset(PACKAGE_RULES)
    | frozenset(rule for table in LANGUAGE_RULES.values() for rule in table)
)
