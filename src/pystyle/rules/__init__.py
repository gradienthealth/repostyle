"""Repo-style lint rules not covered by ruff or other off-the-shelf tools.

Each rule is a function taking `(path, source)` and yielding `Violation`
records, defined in a themed module. This package re-exports the whole
public surface, so `from pystyle.rules import <name>` resolves
regardless of which module the name lives in.
"""

from __future__ import annotations

from pystyle.rules._registry import (
    ALL_RULE_IDS,
    RULE_SEVERITY,
    RULES,
    run_rule,
    severity_of,
)
from pystyle.rules._violation import (
    RS_ACRONYM_CASING,
    RS_BANNED_ABBREVIATION,
    RS_BANNED_IMPORT_BY_PATH,
    RS_BEHAVIOR_VERIFICATION_ONLY,
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
from pystyle.rules.doc_fill import check_doc_fill, reflow_doc_fill
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

__all__ = [
    "ALL_RULE_IDS",
    "RULES",
    "RULE_SEVERITY",
    "RS_ACRONYM_CASING",
    "RS_BANNED_ABBREVIATION",
    "RS_BANNED_IMPORT_BY_PATH",
    "RS_BEHAVIOR_VERIFICATION_ONLY",
    "RS_COGNITIVE_COMPLEXITY",
    "RS_COMMENT_TAG_FORMAT",
    "RS_CONDITIONAL_TEST_LOGIC",
    "RS_DISCOURAGED_CLASS_SUFFIX",
    "RS_DOC_FILL",
    "RS_DOC_VALUE_SIGNAL",
    "RS_DURATION_AS_TIMEDELTA",
    "RS_ELEMENT_ORDER",
    "RS_EXCESSIVE_MOCKING",
    "RS_FIELD_COMMENT_AS_DOCSTRING",
    "RS_FILLER_DOCSTRING_OPENING",
    "RS_NO_ATTRIBUTES_BLOCK",
    "RS_NO_DOUBLE_BACKTICKS",
    "RS_NO_MOCK_PATCH",
    "RS_NO_NEGATED_BOOLEAN",
    "RS_NO_PHI_SAFE_EXC_INFO",
    "RS_PORT_NO_IMPLEMENTATION",
    "RS_SLEEPY_TEST",
    "RS_SUMMARY_COMMENT_AS_DOCSTRING",
    "RS_TEST_NAMING",
    "Severity",
    "Violation",
    "check_acronym_casing",
    "check_banned_abbreviation",
    "check_banned_import_by_path",
    "check_behavior_verification_only",
    "check_class_member_order",
    "check_cognitive_complexity",
    "check_comment_tag_format",
    "check_conditional_test_logic",
    "check_discouraged_class_suffix",
    "check_doc_fill",
    "check_doc_value_signal",
    "check_duration_as_timedelta",
    "check_excessive_mocking",
    "check_field_comment_as_docstring",
    "check_filler_docstring_opening",
    "check_module_element_order",
    "check_no_attributes_block",
    "check_no_double_backticks_in_docstrings",
    "check_no_double_backticks_in_md",
    "check_no_mock_patch",
    "check_no_negated_boolean",
    "check_no_phi_safe_with_exc_info",
    "check_port_no_implementation",
    "check_sleepy_test",
    "check_summary_comment_as_docstring",
    "check_test_naming",
    "reflow_doc_fill",
    "run_rule",
    "severity_of",
]
