import pytest

from repostyle.explain import discovery_hint, explain_rule
from repostyle.rules import (
    ABBREVIATION_EXPANSIONS,
    ALL_RULE_IDS,
    RULE_DOCS,
    has_guidance,
)
from repostyle.rules.naming import BANNED_ABBREVIATIONS

_RICH_RULES = ["RS010", "RS012", "RS015", "RS016", "RS017", "RS018", "RS022"]
_SUMMARY_ONLY_RULES = ["RS001", "RS002", "RS004"]


class TestRuleDocs:
    def test_EveryRule_HasACatalogEntry(self) -> None:
        assert set(RULE_DOCS) == set(ALL_RULE_IDS)

    def test_AbbreviationExpansions_CoverExactlyTheBannedSet(self) -> None:
        assert set(ABBREVIATION_EXPANSIONS) == set(BANNED_ABBREVIATIONS)


class TestExplainRule:
    @pytest.mark.parametrize(
        "rule_id, present, absent",
        [
            (
                "RS010",
                [
                    "RS010  banned-abbreviation  (error)",
                    "Why:",
                    "Examples:",
                    "bad:",
                    "good:",
                    "Reference:",
                    "cfg -> configuration",
                ],
                [],
            ),
            ("RS012", ["Likely causes and remedies:", "(warning)"], ["Examples:"]),
            ("RS001", ["Fixable: no."], ["Why:", "Examples:", "Reference:"]),
        ],
        ids=["rich-with-reference", "heuristic-warning", "summary-only"],
    )
    def test_RuleCard_RendersOnlyItsApplicableSections(
        self, rule_id: str, present: list[str], absent: list[str]
    ) -> None:
        """An empty `RuleDoc` field gates its section out of the card."""
        card = explain_rule(rule_id)
        assert card is not None
        assert not [marker for marker in present if marker not in card]
        assert not [marker for marker in absent if marker in card]

    def test_FixableRule_StatesTheFixCommand(self) -> None:
        card = explain_rule("RS009")
        assert card is not None
        assert "Fixable: yes — rerun with `repostyle --fix`." in card

    def test_UnknownRule_ReturnsNone(self) -> None:
        assert explain_rule("RS999") is None


class TestDiscoveryHint:
    def test_RuleId_FormatsThePointer(self) -> None:
        hint = discovery_hint("RS010")
        assert hint == "→ run 'repostyle explain RS010' for guidance and examples"


class TestHasGuidance:
    @pytest.mark.parametrize("rule_id", _RICH_RULES, ids=_RICH_RULES)
    def test_RichRule_HasGuidance(self, rule_id: str) -> None:
        assert has_guidance(rule_id) is True

    @pytest.mark.parametrize("rule_id", _SUMMARY_ONLY_RULES, ids=_SUMMARY_ONLY_RULES)
    def test_SummaryOnlyRule_HasNoGuidance(self, rule_id: str) -> None:
        assert has_guidance(rule_id) is False

    def test_UnknownRule_HasNoGuidance(self) -> None:
        assert has_guidance("RS999") is False
