from pathlib import Path

import pytest

from repostyle.rules import (
    RS_ACRONYM_CASING,
    RS_DISCOURAGED_CLASS_SUFFIX,
    Violation,
)
from repostyle.suppressions import filter_suppressed

_PATH = Path("module.py")
_BOTH_RULES = [
    Violation(1, 1, RS_ACRONYM_CASING, "acronym"),
    Violation(1, 1, RS_DISCOURAGED_CLASS_SUFFIX, "suffix"),
]


class TestFilterSuppressed:
    @pytest.mark.parametrize(
        ("directive", "kept"),
        [
            ("# style: ignore[RS001]", [RS_DISCOURAGED_CLASS_SUFFIX]),
            ("# style: ignore", []),
            ("# style: ignore[RS001, RS011]", []),
            ("# style: ignore[]", [RS_ACRONYM_CASING, RS_DISCOURAGED_CLASS_SUFFIX]),
        ],
        ids=["one_rule", "all_rules", "rule_list", "empty_brackets_suppress_none"],
    )
    def test_LineDirective_DropsMatchingRulesOnThatLine(
        self, directive: str, kept: list[str]
    ) -> None:
        source = f"class FhirManager: ...  {directive}\n"
        result = filter_suppressed(_PATH, _BOTH_RULES, source)
        assert [v.rule for v in result] == kept

    def test_IgnoreFile_DropsEveryFinding(self) -> None:
        source = "# style: ignore-file\nclass FhirManager: ...\n"
        findings = [Violation(2, 1, RS_ACRONYM_CASING, "acronym")]
        assert filter_suppressed(_PATH, findings, source) == []

    def test_IgnoreFileBeforeUntokenizableTail_StillSuppresses(self) -> None:
        source = '# style: ignore-file\nx = "unterminated\n'
        findings = [Violation(2, 1, RS_ACRONYM_CASING, "acronym")]
        assert filter_suppressed(_PATH, findings, source) == []

    def test_DirectiveOnAnotherLine_KeepsFinding(self) -> None:
        source = "x = 1  # style: ignore[RS001]\nclass FhirClient: ...\n"
        findings = [Violation(2, 1, RS_ACRONYM_CASING, "acronym")]
        assert filter_suppressed(_PATH, findings, source) == findings

    def test_NoDirective_KeepsEveryFinding(self) -> None:
        source = "class FhirManager: ...\n"
        assert filter_suppressed(_PATH, _BOTH_RULES, source) == _BOTH_RULES

    @pytest.mark.parametrize(
        ("path", "source"),
        [
            (Path("c.toml"), "key = 1  # style: ignore[RS001]\n"),
            (Path("c.yaml"), "key: 1  # style: ignore[RS001]\n"),
        ],
        ids=["toml", "yaml"],
    )
    def test_LineDirectiveInConfigLanguage_Suppresses(
        self, path: Path, source: str
    ) -> None:
        findings = [Violation(1, 1, RS_ACRONYM_CASING, "acronym")]
        assert filter_suppressed(path, findings, source) == []
