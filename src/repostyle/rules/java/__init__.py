"""Java implementations of the rules, bound to Java files alone.

A rule id names one concern in every language: RS001 is acronym casing in a
Java name as in a Python one, though each language's convention decides the
casing. The checks here read Java syntax, so the registry hands them only Java
files and they carry no suffix guard of their own.
"""

from repostyle.rules._violation import (
    RS_ACRONYM_CASING,
    RS_ARG_DESCRIBED_IN_PROSE,
    RS_BANNED_ABBREVIATION,
    RS_CONDITIONAL_TEST_LOGIC,
    RS_DISCOURAGED_CLASS_SUFFIX,
    RS_DURATION_AS_TIMEDELTA,
    RS_EMPTY_CATCH_REASON,
    RS_NO_MOCK_PATCH,
    RS_RECORD_COMPONENT_UNDOCUMENTED,
    RS_SLEEPY_TEST,
    RS_TEST_NAMING,
    RS_TOO_MANY_POSITIONAL_ARGS,
)
from repostyle.rules.java._contracts import (
    check_java_duration_constant,
    check_java_param_described_in_prose,
    check_java_too_many_parameters,
    check_record_component_tags,
)
from repostyle.rules.java._errors import check_empty_catch_reason
from repostyle.rules.java._naming import (
    check_java_acronym_as_word,
    check_java_banned_abbreviation,
    check_java_discouraged_class_suffix,
)
from repostyle.rules.java._testing import (
    check_java_conditional_test_logic,
    check_java_no_mock_library,
    check_java_sleepy_test,
    check_java_test_naming,
)

RULES = {
    RS_ACRONYM_CASING: (check_java_acronym_as_word,),
    RS_BANNED_ABBREVIATION: (check_java_banned_abbreviation,),
    RS_DISCOURAGED_CLASS_SUFFIX: (check_java_discouraged_class_suffix,),
    RS_DURATION_AS_TIMEDELTA: (check_java_duration_constant,),
    RS_TOO_MANY_POSITIONAL_ARGS: (check_java_too_many_parameters,),
    RS_ARG_DESCRIBED_IN_PROSE: (check_java_param_described_in_prose,),
    RS_RECORD_COMPONENT_UNDOCUMENTED: (check_record_component_tags,),
    RS_TEST_NAMING: (check_java_test_naming,),
    RS_NO_MOCK_PATCH: (check_java_no_mock_library,),
    RS_CONDITIONAL_TEST_LOGIC: (check_java_conditional_test_logic,),
    RS_SLEEPY_TEST: (check_java_sleepy_test,),
    RS_EMPTY_CATCH_REASON: (check_empty_catch_reason,),
}

__all__ = [
    "RULES",
    "check_empty_catch_reason",
    "check_java_acronym_as_word",
    "check_java_banned_abbreviation",
    "check_java_conditional_test_logic",
    "check_java_discouraged_class_suffix",
    "check_java_duration_constant",
    "check_java_no_mock_library",
    "check_java_param_described_in_prose",
    "check_java_sleepy_test",
    "check_java_test_naming",
    "check_java_too_many_parameters",
    "check_record_component_tags",
]
