"""The `Violation` record, rule severities, and the `RSnnn` rule id constants."""

from __future__ import annotations

import enum
from typing import NamedTuple


class Severity(enum.Enum):
    """How a rule's findings affect the exit status.

    An error-severity finding fails the run; a warning-severity finding
    is advisory and printed but does not fail it.
    """

    ERROR = "error"
    WARNING = "warning"


class Violation(NamedTuple):
    line: int
    """1-based line the violation points at."""
    col: int
    """1-based column the violation points at."""
    rule: str
    """The `RSnnn` id of the rule that produced it."""
    message: str
    """Human-readable description of what to fix."""


RS_ACRONYM_CASING = "RS001"
RS_TEST_NAMING = "RS002"
RS_NO_MOCK_PATCH = "RS003"
RS_NO_ATTRIBUTES_BLOCK = "RS004"
RS_NO_DOUBLE_BACKTICKS = "RS005"
RS_PORT_NO_IMPLEMENTATION = "RS006"
RS_DURATION_AS_TIMEDELTA = "RS007"
RS_NO_PHI_SAFE_EXC_INFO = "RS008"
RS_DOC_FILL = "RS009"
RS_BANNED_ABBREVIATION = "RS010"
RS_DISCOURAGED_CLASS_SUFFIX = "RS011"
RS_COGNITIVE_COMPLEXITY = "RS012"
RS_CONDITIONAL_TEST_LOGIC = "RS013"
RS_SLEEPY_TEST = "RS014"
RS_EXCESSIVE_MOCKING = "RS015"
RS_BEHAVIOR_VERIFICATION_ONLY = "RS016"
RS_BANNED_IMPORT_BY_PATH = "RS017"
RS_DOC_VALUE_SIGNAL = "RS018"
RS_ELEMENT_ORDER = "RS019"
RS_SUMMARY_COMMENT_AS_DOCSTRING = "RS020"
RS_FIELD_COMMENT_AS_DOCSTRING = "RS021"
RS_COMMENT_TAG_FORMAT = "RS022"
RS_FILLER_DOCSTRING_OPENING = "RS023"
RS_NO_NEGATED_BOOLEAN = "RS024"
