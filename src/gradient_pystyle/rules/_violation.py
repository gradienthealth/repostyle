"""The `Violation` record and the `RSnnn` rule id constants."""

from __future__ import annotations

from typing import NamedTuple


class Violation(NamedTuple):
    line: int
    rule: str
    message: str


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
