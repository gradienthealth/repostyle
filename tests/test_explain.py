import pytest

from pystyle.explain import discovery_hint, explain_rule
from pystyle.rules import ABBREVIATION_EXPANSIONS, ALL_RULE_IDS, RULE_DOCS, has_guidance
from pystyle.rules.naming import BANNED_ABBREVIATIONS

_RICH_RULES = ["RS010", "RS012", "RS015", "RS016", "RS017", "RS018", "RS022"]
_SUMMARY_ONLY_RULES = ["RS001", "RS002", "RS004"]


class TestRuleDocs:
    def test_EveryRule_HasACatalogEntry(self) -> None:
        assert set(RULE_DOCS) == set(ALL_RULE_IDS)

    def test_AbbreviationExpansions_CoverExactlyTheBannedSet(self) -> None:
        assert set(ABBREVIATION_EXPANSIONS) == set(BANNED_ABBREVIATIONS)


class TestExplainRule:
    def test_RuleWithExamples_RendersEverySection(self) -> None:
        card = explain_rule("RS010")
        assert card is not None
        assert "RS010  banned-abbreviation  (error)" in card
        assert "Why:" in card
        assert "Examples:" in card and "bad:" in card and "good:" in card
        assert "Reference:" in card and "cfg -> configuration" in card

    def test_FixableRule_StatesTheFixCommand(self) -> None:
        card = explain_rule("RS009")
        assert card is not None
        assert "Fixable: yes — rerun with `pystyle --fix`." in card

    def test_HeuristicRule_RendersTheCausesSection(self) -> None:
        card = explain_rule("RS012")
        assert card is not None
        assert "Likely causes and remedies:" in card
        assert "Examples:" not in card

    def test_WarningRule_LabelsItsSeverity(self) -> None:
        card = explain_rule("RS012")
        assert card is not None
        assert "(warning)" in card

    def test_SummaryOnlyRule_OmitsRichSections(self) -> None:
        card = explain_rule("RS001")
        assert card is not None
        assert "Fixable: no." in card
        assert "Why:" not in card
        assert "Examples:" not in card
        assert "Reference:" not in card

    def test_UnknownRule_ReturnsNone(self) -> None:
        assert explain_rule("RS999") is None


class TestDiscoveryHint:
    def test_RuleId_FormatsThePointer(self) -> None:
        hint = discovery_hint("RS010")
        assert hint == "→ run 'pystyle explain RS010' for guidance and examples"


class TestHasGuidance:
    @pytest.mark.parametrize("rule_id", _RICH_RULES, ids=_RICH_RULES)
    def test_RichRule_HasGuidance(self, rule_id: str) -> None:
        assert has_guidance(rule_id) is True

    @pytest.mark.parametrize("rule_id", _SUMMARY_ONLY_RULES, ids=_SUMMARY_ONLY_RULES)
    def test_SummaryOnlyRule_HasNoGuidance(self, rule_id: str) -> None:
        assert has_guidance(rule_id) is False

    def test_UnknownRule_HasNoGuidance(self) -> None:
        assert has_guidance("RS999") is False
