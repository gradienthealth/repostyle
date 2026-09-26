"""Rule documentation catalog backed by validated package data."""

from __future__ import annotations

import tomllib
from importlib.resources import files
from typing import Any

from repostyle.rules._catalog_types import ABBREVIATION_EXPANSIONS, Example, RuleDoc

__all__ = [
    "ABBREVIATION_EXPANSIONS",
    "RULE_DOCS",
    "Example",
    "RuleDoc",
    "has_guidance",
    "rule_doc",
]


def _load_catalog() -> dict[str, RuleDoc]:
    """Loads and validates the bundled TOML catalog."""
    resource = files("repostyle.rules").joinpath("catalog.toml")
    with resource.open("rb") as catalog_file:
        records = tomllib.load(catalog_file)
    catalog: dict[str, RuleDoc] = {}
    for rule_id, value in records.items():
        if not isinstance(value, dict):
            raise TypeError(f"catalog entry {rule_id} must be a table")
        catalog[rule_id] = RuleDoc(
            name=_string(value, "name", rule_id),
            summary=_string(value, "summary", rule_id),
            rationale=_string(value, "rationale", rule_id),
            examples=_examples(value, rule_id),
            signals=_strings(value, "signals", rule_id),
            reference=_strings(value, "reference", rule_id),
        )
    return catalog


def _examples(record: dict[str, Any], rule_id: str) -> tuple[Example, ...]:
    """Returns validated examples from one catalog record."""
    value = record.get("examples")
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise TypeError(f"catalog entry {rule_id} has invalid `examples`")
    return tuple(
        Example(
            bad=_string(item, "bad", rule_id),
            good=_string(item, "good", rule_id),
            note=_string(item, "note", rule_id),
        )
        for item in value
    )


def _string(record: dict[str, Any], field: str, rule_id: str) -> str:
    """Returns a required string from one catalog record."""
    value = record.get(field)
    if not isinstance(value, str):
        raise TypeError(f"catalog entry {rule_id} has invalid `{field}`")
    return value


def _strings(record: dict[str, Any], field: str, rule_id: str) -> tuple[str, ...]:
    """Returns a required string array from one catalog record."""
    value = record.get(field)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError(f"catalog entry {rule_id} has invalid `{field}`")
    return tuple(value)


RULE_DOCS = _load_catalog()


def rule_doc(rule_id: str) -> RuleDoc | None:
    """Returns a rule's metadata record, or `None` for an unknown id."""
    return RULE_DOCS.get(rule_id)


def has_guidance(rule_id: str) -> bool:
    """Reports whether a rule carries detail past its one-line summary."""
    doc = RULE_DOCS.get(rule_id)
    return doc is not None and bool(doc.examples or doc.signals or doc.reference)
