"""The rule registry mapping ids to check functions, plus `run_rule`."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

from pystyle.rules._violation import (
    RS_ACRONYM_CASING,
    RS_BANNED_ABBREVIATION,
    RS_BANNED_IMPORT_BY_PATH,
    RS_BEHAVIOR_VERIFICATION_ONLY,
    RS_BOOLEAN_PREFIX_REQUIRED,
    RS_COGNITIVE_COMPLEXITY,
    RS_COMMENT_TAG_FORMAT,
    RS_CONDITIONAL_TEST_LOGIC,
    RS_DISCOURAGED_CLASS_SUFFIX,
    RS_DOC_FILL,
    RS_DOC_VALUE_SIGNAL,
    RS_DURATION_AS_TIMEDELTA,
    RS_ELEMENT_ORDER,
    RS_EXCESSIVE_MOCKING,
    RS_FIELD_COMMENT_AS_DOCSTRING,
    RS_FILLER_DOCSTRING_OPENING,
    RS_NO_ATTRIBUTES_BLOCK,
    RS_NO_DOUBLE_BACKTICKS,
    RS_NO_MOCK_PATCH,
    RS_NO_NEGATED_BOOLEAN,
    RS_NO_PHI_SAFE_EXC_INFO,
    RS_PORT_NO_IMPLEMENTATION,
    RS_SLEEPY_TEST,
    RS_SUMMARY_COMMENT_AS_DOCSTRING,
    RS_TEST_NAMING,
    Severity,
    Violation,
)
from pystyle.rules.comments import check_comment_tag_format
from pystyle.rules.complexity import check_cognitive_complexity
from pystyle.rules.doc_fill import check_doc_fill
from pystyle.rules.doc_value import check_doc_value_signal
from pystyle.rules.docstrings import (
    check_field_comment_as_docstring,
    check_filler_docstring_opening,
    check_no_attributes_block,
    check_no_double_backticks_in_docstrings,
    check_no_double_backticks_in_md,
    check_summary_comment_as_docstring,
)
from pystyle.rules.duration import check_duration_as_timedelta
from pystyle.rules.import_layering import check_banned_import_by_path
from pystyle.rules.layout import (
    check_class_member_order,
    check_module_element_order,
)
from pystyle.rules.logging_phi import check_no_phi_safe_with_exc_info
from pystyle.rules.naming import (
    check_acronym_casing,
    check_banned_abbreviation,
    check_boolean_prefix_required,
    check_discouraged_class_suffix,
    check_no_negated_boolean,
)
from pystyle.rules.ports import check_port_no_implementation
from pystyle.rules.testing import (
    check_behavior_verification_only,
    check_conditional_test_logic,
    check_excessive_mocking,
    check_no_mock_patch,
    check_sleepy_test,
    check_test_naming,
)

RULES: dict[str, tuple[Callable[[Path, str], Iterator[Violation]], ...]] = {
    RS_ACRONYM_CASING: (check_acronym_casing,),
    RS_TEST_NAMING: (check_test_naming,),
    RS_NO_MOCK_PATCH: (check_no_mock_patch,),
    RS_NO_ATTRIBUTES_BLOCK: (check_no_attributes_block,),
    RS_NO_DOUBLE_BACKTICKS: (
        check_no_double_backticks_in_md,
        check_no_double_backticks_in_docstrings,
    ),
    RS_PORT_NO_IMPLEMENTATION: (check_port_no_implementation,),
    RS_DURATION_AS_TIMEDELTA: (check_duration_as_timedelta,),
    RS_NO_PHI_SAFE_EXC_INFO: (check_no_phi_safe_with_exc_info,),
    RS_DOC_FILL: (check_doc_fill,),
    RS_BANNED_ABBREVIATION: (check_banned_abbreviation,),
    RS_DISCOURAGED_CLASS_SUFFIX: (check_discouraged_class_suffix,),
    RS_NO_NEGATED_BOOLEAN: (check_no_negated_boolean,),
    RS_BOOLEAN_PREFIX_REQUIRED: (check_boolean_prefix_required,),
    RS_COGNITIVE_COMPLEXITY: (check_cognitive_complexity,),
    RS_CONDITIONAL_TEST_LOGIC: (check_conditional_test_logic,),
    RS_SLEEPY_TEST: (check_sleepy_test,),
    RS_EXCESSIVE_MOCKING: (check_excessive_mocking,),
    RS_BEHAVIOR_VERIFICATION_ONLY: (check_behavior_verification_only,),
    RS_BANNED_IMPORT_BY_PATH: (check_banned_import_by_path,),
    RS_DOC_VALUE_SIGNAL: (check_doc_value_signal,),
    RS_ELEMENT_ORDER: (check_module_element_order, check_class_member_order),
    RS_SUMMARY_COMMENT_AS_DOCSTRING: (check_summary_comment_as_docstring,),
    RS_FIELD_COMMENT_AS_DOCSTRING: (check_field_comment_as_docstring,),
    RS_COMMENT_TAG_FORMAT: (check_comment_tag_format,),
    RS_FILLER_DOCSTRING_OPENING: (check_filler_docstring_opening,),
}


# A threshold- or judgment-adjacent rule registers Severity.WARNING here
# to emit an advisory, non-blocking signal; the mechanical, low-false-
# positive rules stay at the default ERROR and fail the run.
RULE_SEVERITY: dict[str, Severity] = {
    RS_COGNITIVE_COMPLEXITY: Severity.WARNING,
    RS_EXCESSIVE_MOCKING: Severity.WARNING,
    RS_BEHAVIOR_VERIFICATION_ONLY: Severity.WARNING,
    RS_DOC_VALUE_SIGNAL: Severity.WARNING,
    RS_ELEMENT_ORDER: Severity.WARNING,
    RS_SUMMARY_COMMENT_AS_DOCSTRING: Severity.WARNING,
    RS_FIELD_COMMENT_AS_DOCSTRING: Severity.WARNING,
    RS_NO_NEGATED_BOOLEAN: Severity.WARNING,
    RS_BOOLEAN_PREFIX_REQUIRED: Severity.WARNING,
}


def severity_of(rule_id: str) -> Severity:
    """Return a rule's severity, defaulting to `ERROR`."""
    return RULE_SEVERITY.get(rule_id, Severity.ERROR)


def run_rule(rule_id: str, path: Path, source: str) -> Iterator[Violation]:
    """Run a single rule by id over one source, yielding its violations.

    A rule id maps to one or more check functions; e.g. RS005 runs both
    the markdown and the Python-docstring backtick checks.
    """
    for check in RULES.get(rule_id, ()):
        yield from check(path, source)


ALL_RULE_IDS: frozenset[str] = frozenset(RULES)
