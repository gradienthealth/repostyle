"""A partition of the single-file rule registry."""

from repostyle.rules._violation import (
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
    RS_FILE_LITERAL_RESTATEMENT,
    RS_GCP_BARE_IDENTIFIER,
    RS_NO_ATTRIBUTES_BLOCK,
    RS_NO_DOUBLE_BACKTICKS,
    RS_NO_MAKE_IN_PRODUCTION,
    RS_NO_MOCK_PATCH,
    RS_NO_NEGATED_BOOLEAN,
    RS_NO_PHI_SAFE_EXC_INFO,
    RS_PORT_NO_IMPLEMENTATION,
    RS_REPEATED_TEST_SETUP,
    RS_SLEEPY_TEST,
    RS_SOURCE_MODULE_SIZE,
    RS_SUMMARY_COMMENT_AS_DOCSTRING,
    RS_TAG_COMMENT_CONTINUATION_INDENT,
    RS_TEST_MODULE_SIZE,
    RS_TEST_NAMING,
    RS_TEST_PARAMETRIZATION_CANDIDATE,
)
from repostyle.rules.comments import (
    check_comment_tag_format,
    check_tag_comment_continuation_indent,
)
from repostyle.rules.complexity import check_cognitive_complexity
from repostyle.rules.doc_fill import check_doc_fill
from repostyle.rules.doc_value import check_doc_value_signal
from repostyle.rules.docstrings import (
    check_field_comment_as_docstring,
    check_no_attributes_block,
    check_no_double_backticks_in_docstrings,
    check_no_double_backticks_in_md,
    check_summary_comment_as_docstring,
)
from repostyle.rules.duration import check_duration_as_timedelta
from repostyle.rules.import_layering import check_banned_import_by_path
from repostyle.rules.layout import (
    check_class_member_order,
    check_module_element_order,
)
from repostyle.rules.logging_phi import check_no_phi_safe_with_exc_info
from repostyle.rules.module_size import (
    check_source_module_size,
    check_test_module_size,
)
from repostyle.rules.naming import (
    check_acronym_casing,
    check_banned_abbreviation,
    check_boolean_prefix_required,
    check_discouraged_class_suffix,
    check_gcp_bare_identifier,
    check_no_make_in_production,
    check_no_negated_boolean,
)
from repostyle.rules.ports import check_port_no_implementation
from repostyle.rules.testing import (
    check_behavior_verification_only,
    check_conditional_test_logic,
    check_excessive_mocking,
    check_file_literal_restatement,
    check_no_mock_patch,
    check_sleepy_test,
    check_test_naming,
)
from repostyle.rules.testing_reuse import (
    check_repeated_test_setup,
    check_test_parametrization_candidate,
)

RULES_PART = {
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
    RS_NO_MAKE_IN_PRODUCTION: (check_no_make_in_production,),
    RS_GCP_BARE_IDENTIFIER: (check_gcp_bare_identifier,),
    RS_COGNITIVE_COMPLEXITY: (check_cognitive_complexity,),
    RS_CONDITIONAL_TEST_LOGIC: (check_conditional_test_logic,),
    RS_SLEEPY_TEST: (check_sleepy_test,),
    RS_EXCESSIVE_MOCKING: (check_excessive_mocking,),
    RS_BEHAVIOR_VERIFICATION_ONLY: (check_behavior_verification_only,),
    RS_FILE_LITERAL_RESTATEMENT: (check_file_literal_restatement,),
    RS_TEST_MODULE_SIZE: (check_test_module_size,),
    RS_TEST_PARAMETRIZATION_CANDIDATE: (check_test_parametrization_candidate,),
    RS_REPEATED_TEST_SETUP: (check_repeated_test_setup,),
    RS_SOURCE_MODULE_SIZE: (check_source_module_size,),
    RS_BANNED_IMPORT_BY_PATH: (check_banned_import_by_path,),
    RS_DOC_VALUE_SIGNAL: (check_doc_value_signal,),
    RS_ELEMENT_ORDER: (check_module_element_order, check_class_member_order),
    RS_SUMMARY_COMMENT_AS_DOCSTRING: (check_summary_comment_as_docstring,),
    RS_FIELD_COMMENT_AS_DOCSTRING: (check_field_comment_as_docstring,),
    RS_COMMENT_TAG_FORMAT: (check_comment_tag_format,),
    RS_TAG_COMMENT_CONTINUATION_INDENT: (check_tag_comment_continuation_indent,),
}
