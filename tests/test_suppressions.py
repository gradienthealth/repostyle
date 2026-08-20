from pathlib import Path

import pytest

from repostyle.rules import (
    RS_ACRONYM_CASING,
    RS_DISCOURAGED_CLASS_SUFFIX,
    Violation,
)
from repostyle.suppressions import filter_suppressed, suppressed_lines

_PATH = Path("module.py")
_BOTH_RULES = [
    Violation(1, 1, RS_ACRONYM_CASING, "acronym"),
    Violation(1, 1, RS_DISCOURAGED_CLASS_SUFFIX, "suffix"),
]
_DECORATED_CLASS = """\
# style: ignore-block[RS001]
@dataclass
class FhirManager:
    def load(self) -> None: ...

class FhirClient: ...
"""
_METHOD_IN_CLASS = """\
class Outer:
    # style: ignore-block[RS001]
    def fhir_load(self) -> None:
        x = 1

    def fhir_save(self) -> None:
        y = 2
"""
_TRAILING_ON_DEF = """\
def load() -> None:  # style: ignore-block[RS001]
    x = 1
    y = 2

def save() -> None: ...
"""
_COMPOUND_ON_ONE_LINE = """\
# style: ignore-block[RS001]
if flag: x = 1
else: y = 2

z = 3
"""


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

    @pytest.mark.parametrize(
        ("source", "suppressed", "kept"),
        [
            (_DECORATED_CLASS, [2, 3, 4], [6]),
            (_METHOD_IN_CLASS, [3, 4], [6, 7]),
            (_TRAILING_ON_DEF, [1, 2, 3], [5]),
            (_COMPOUND_ON_ONE_LINE, [2, 3], [5]),
        ],
        ids=[
            "above_decorated_class",
            "above_method",
            "trailing_on_def_line",
            "outermost_of_two_statements_starting_together",
        ],
    )
    def test_BlockDirective_CoversTheAttachedStatementSpan(
        self, source: str, suppressed: list[int], kept: list[int]
    ) -> None:
        findings = [
            Violation(line, 1, RS_ACRONYM_CASING, "acronym")
            for line in suppressed + kept
        ]
        result = filter_suppressed(_PATH, findings, source)
        assert [v.line for v in result] == kept

    def test_BlockDirective_LeavesUnnamedRulesAlone(self) -> None:
        source = "# style: ignore-block[RS001]\nclass FhirManager: ...\n"
        findings = [
            Violation(2, 1, RS_ACRONYM_CASING, "acronym"),
            Violation(2, 1, RS_DISCOURAGED_CLASS_SUFFIX, "suffix"),
        ]
        result = filter_suppressed(_PATH, findings, source)
        assert [v.rule for v in result] == [RS_DISCOURAGED_CLASS_SUFFIX]

    def test_UnbracketedBlockDirective_CoversEveryRuleInTheSpan(self) -> None:
        source = "# style: ignore-block\nclass FhirManager:\n    x = 1\n"
        findings = [
            Violation(2, 1, RS_ACRONYM_CASING, "acronym"),
            Violation(3, 1, RS_DISCOURAGED_CLASS_SUFFIX, "suffix"),
        ]
        assert filter_suppressed(_PATH, findings, source) == []

    def test_IgnoreFile_DropsEveryFinding(self) -> None:
        source = "# style: ignore-file\nclass FhirManager: ...\n"
        findings = [Violation(2, 1, RS_ACRONYM_CASING, "acronym")]
        assert filter_suppressed(_PATH, findings, source) == []

    def test_IgnoreFileNamingARule_DropsOnlyThatRule(self) -> None:
        source = "# style: ignore-file[RS001]\nclass FhirManager: ...\n"
        findings = [
            Violation(2, 1, RS_ACRONYM_CASING, "acronym"),
            Violation(2, 1, RS_DISCOURAGED_CLASS_SUFFIX, "suffix"),
        ]
        result = filter_suppressed(_PATH, findings, source)
        assert [v.rule for v in result] == [RS_DISCOURAGED_CLASS_SUFFIX]

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

    @pytest.mark.parametrize(
        ("path", "source", "directive_line"),
        [
            (_PATH, "class FhirManager: ...\n# style: ignore-block[RS001]\n", 2),
            (_PATH, '# style: ignore-block[RS001]\nx = "unterminated\n', 1),
            (Path("c.yaml"), "key: 1  # style: ignore-block[RS001]\n", 1),
        ],
        ids=["no_statement_follows", "unparsable_python", "no_ast_language"],
    )
    def test_UnattachableBlockDirective_FallsBackToItsOwnLine(
        self, path: Path, source: str, directive_line: int
    ) -> None:
        findings = [Violation(line, 1, RS_ACRONYM_CASING, "acronym") for line in (1, 2)]
        result = filter_suppressed(path, findings, source)
        assert [v.line for v in result] == [
            line for line in (1, 2) if line != directive_line
        ]


class TestSuppressedLines:
    def test_BlockDirective_ReportsEveryLineOfTheSpan(self) -> None:
        file_suppressed, lines = suppressed_lines(
            _PATH, _TRAILING_ON_DEF, RS_ACRONYM_CASING
        )
        assert (file_suppressed, lines) == (False, frozenset({1, 2, 3}))

    @pytest.mark.parametrize(
        ("directive", "rule", "is_suppressed"),
        [
            ("# style: ignore-file", RS_ACRONYM_CASING, True),
            ("# style: ignore-file[RS001]", RS_ACRONYM_CASING, True),
            ("# style: ignore-file[RS001]", RS_DISCOURAGED_CLASS_SUFFIX, False),
        ],
        ids=["unbracketed", "named_rule", "unnamed_rule"],
    )
    def test_FileDirective_ScopesToItsRuleList(
        self, directive: str, rule: str, *, is_suppressed: bool
    ) -> None:
        source = f"{directive}\nclass FhirManager: ...\n"
        file_suppressed, _ = suppressed_lines(_PATH, source, rule)
        assert file_suppressed is is_suppressed
