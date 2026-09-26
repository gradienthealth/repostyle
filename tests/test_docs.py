import re
from pathlib import Path

from repostyle.rules import ALL_RULE_IDS
from repostyle.rules._registry import FIXABLE_RULES, RULE_SEVERITY
from repostyle.rules._violation import Severity

_RULE_REFERENCE = Path(__file__).resolve().parent.parent / "docs" / "rules.md"
_TABLE_ROW = re.compile(r"^\| (RS\d{3}) \| (error|warning) \|", re.MULTILINE)
_FIX_ROW = re.compile(r"^\| (RS\d{3}) \| [A-Z]", re.MULTILINE)


class TestRuleReferenceTables:
    def test_EveryRule_HasATableRow(self) -> None:
        assert set(_rule_table()) == set(ALL_RULE_IDS)

    def test_EveryTableRow_StatesTheDefaultSeverity(self) -> None:
        documented = _rule_table()
        actual = {
            rule_id: RULE_SEVERITY.get(rule_id, Severity.ERROR).value
            for rule_id in documented
        }
        assert documented == actual

    def test_FixableRules_AreListedInTheFixTable(self) -> None:
        configuration = (_RULE_REFERENCE.parent / "configuration.md").read_text(
            encoding="utf-8"
        )
        section = configuration.split("## Fix safe findings", 1)[1].split("\n## ", 1)[0]
        assert set(_FIX_ROW.findall(section)) == set(FIXABLE_RULES)


class TestRuleReferenceCounts:
    def test_StatedTotal_MatchesTheRegistry(self) -> None:
        text = _RULE_REFERENCE.read_text(encoding="utf-8")
        assert f"ships {len(ALL_RULE_IDS)} rules" in text

    def test_StatedSeveritySplit_MatchesTheRegistry(self) -> None:
        severities = list(_rule_table().values())
        errors = severities.count("error")
        warnings = severities.count("warning")
        text = " ".join(_RULE_REFERENCE.read_text(encoding="utf-8").split())
        assert f"{errors} rules hard-fail and the other {warnings}" in text
        assert f"Those {errors} are the mechanical rules" in text


def _rule_table() -> dict[str, str]:
    """Returns id-to-severity pairs from the rule reference tables."""
    return dict(_TABLE_ROW.findall(_RULE_REFERENCE.read_text(encoding="utf-8")))
