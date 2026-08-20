import re
from pathlib import Path

from repostyle.rules import ALL_RULE_IDS
from repostyle.rules._registry import FIXABLE_RULES, RULE_SEVERITY
from repostyle.rules._violation import Severity

_README = Path(__file__).resolve().parent.parent / "README.md"
_TABLE_ROW = re.compile(r"^\| (RS\d{3}) \| (error|warning) \|", re.MULTILINE)
_FIX_ROW = re.compile(r"^\| (RS\d{3}) \| [A-Z]", re.MULTILINE)


class TestReadmeRuleTables:
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
        text = _README.read_text(encoding="utf-8")
        section = text.split("## Fix findings in place", 1)[1].split("\n## ", 1)[0]
        assert set(_FIX_ROW.findall(section)) == set(FIXABLE_RULES)


def _rule_table() -> dict[str, str]:
    """Returns the id-to-severity pairs the README's rule tables list."""
    return dict(_TABLE_ROW.findall(_README.read_text(encoding="utf-8")))
