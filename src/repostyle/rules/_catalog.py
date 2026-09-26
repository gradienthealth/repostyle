"""Agent-facing metadata for rule explanations."""

from repostyle.rules._catalog_part_1 import RULE_DOCS_PART as _PART_1
from repostyle.rules._catalog_part_2 import RULE_DOCS_PART as _PART_2
from repostyle.rules._catalog_part_3 import RULE_DOCS_PART as _PART_3
from repostyle.rules._catalog_part_4 import RULE_DOCS_PART as _PART_4
from repostyle.rules._catalog_part_5 import RULE_DOCS_PART as _PART_5
from repostyle.rules._catalog_part_6 import RULE_DOCS_PART as _PART_6
from repostyle.rules._catalog_part_7 import RULE_DOCS_PART as _PART_7
from repostyle.rules._catalog_part_8 import RULE_DOCS_PART as _PART_8
from repostyle.rules._catalog_part_9 import RULE_DOCS_PART as _PART_9
from repostyle.rules._catalog_types import (
    ABBREVIATION_EXPANSIONS,
    Example,
    RuleDoc,
)

__all__ = [
    "ABBREVIATION_EXPANSIONS",
    "RULE_DOCS",
    "Example",
    "RuleDoc",
    "has_guidance",
    "rule_doc",
]

RULE_DOCS: dict[str, RuleDoc] = {}
for _part in (
    _PART_1,
    _PART_2,
    _PART_3,
    _PART_4,
    _PART_5,
    _PART_6,
    _PART_7,
    _PART_8,
    _PART_9,
):
    RULE_DOCS.update(_part)


def rule_doc(rule_id: str) -> RuleDoc | None:
    """Returns a rule's metadata record, or `None` for an unknown id."""
    return RULE_DOCS.get(rule_id)


def has_guidance(rule_id: str) -> bool:
    """Reports whether a rule carries detail past its one-line summary.

    True when the rule has examples, heuristic signals, or a reference table --
    the rules whose card is worth fetching, so the discovery hint points only
    at those.
    """
    doc = RULE_DOCS.get(rule_id)
    return doc is not None and bool(doc.examples or doc.signals or doc.reference)
