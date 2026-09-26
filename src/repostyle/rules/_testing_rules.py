"""Binds checks for testing rules."""

from repostyle.rules._violation import (
    RS_BEHAVIOR_VERIFICATION_ONLY,
    RS_CONDITIONAL_TEST_LOGIC,
    RS_EXCESSIVE_MOCKING,
    RS_FILE_LITERAL_RESTATEMENT,
    RS_NO_MOCK_PATCH,
    RS_REPEATED_TEST_SETUP,
    RS_SLEEPY_TEST,
    RS_TEST_MODULE_SIZE,
    RS_TEST_NAMING,
    RS_TEST_PARAMETRIZATION_CANDIDATE,
)
from repostyle.rules.module_size import (
    check_test_module_size,
)
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

RULES = {
    RS_TEST_NAMING: (check_test_naming,),
    RS_NO_MOCK_PATCH: (check_no_mock_patch,),
    RS_CONDITIONAL_TEST_LOGIC: (check_conditional_test_logic,),
    RS_SLEEPY_TEST: (check_sleepy_test,),
    RS_EXCESSIVE_MOCKING: (check_excessive_mocking,),
    RS_BEHAVIOR_VERIFICATION_ONLY: (check_behavior_verification_only,),
    RS_FILE_LITERAL_RESTATEMENT: (check_file_literal_restatement,),
    RS_TEST_MODULE_SIZE: (check_test_module_size,),
    RS_TEST_PARAMETRIZATION_CANDIDATE: (check_test_parametrization_candidate,),
    RS_REPEATED_TEST_SETUP: (check_repeated_test_setup,),
}
