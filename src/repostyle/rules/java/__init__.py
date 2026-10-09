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
    RS_DISCOURAGED_CLASS_SUFFIX,
    RS_DURATION_AS_TIMEDELTA,
    RS_RECORD_COMPONENT_UNDOCUMENTED,
    RS_TOO_MANY_POSITIONAL_ARGS,
)
from repostyle.rules.java._contracts import (
    check_java_duration_constant,
    check_java_param_described_in_prose,
    check_java_too_many_parameters,
    check_record_component_tags,
)
from repostyle.rules.java._naming import (
    check_java_acronym_as_word,
    check_java_banned_abbreviation,
    check_java_discouraged_class_suffix,
)

RULES = {
    RS_ACRONYM_CASING: (check_java_acronym_as_word,),
    RS_BANNED_ABBREVIATION: (check_java_banned_abbreviation,),
    RS_DISCOURAGED_CLASS_SUFFIX: (check_java_discouraged_class_suffix,),
    RS_DURATION_AS_TIMEDELTA: (check_java_duration_constant,),
    RS_TOO_MANY_POSITIONAL_ARGS: (check_java_too_many_parameters,),
    RS_ARG_DESCRIBED_IN_PROSE: (check_java_param_described_in_prose,),
    RS_RECORD_COMPONENT_UNDOCUMENTED: (check_record_component_tags,),
}

__all__ = [
    "RULES",
    "check_java_acronym_as_word",
    "check_java_banned_abbreviation",
    "check_java_discouraged_class_suffix",
    "check_java_duration_constant",
    "check_java_param_described_in_prose",
    "check_java_too_many_parameters",
    "check_record_component_tags",
]
