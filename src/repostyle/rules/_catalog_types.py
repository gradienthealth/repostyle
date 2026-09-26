"""Structured metadata rendered by the rule explanation command."""

from typing import NamedTuple

ABBREVIATION_EXPANSIONS: dict[str, str] = {
    "btn": "button",
    "cfg": "configuration",
    "conn": "connection",
    "ctx": "context",
    "idx": "index",
    "mgr": "manager",
    "mngr": "manager",
    "req": "request",
    "res": "result",
    "resp": "response",
    "usr": "user",
}


class Example(NamedTuple):
    bad: str
    """The violating snippet, shown first so the contrast lands."""
    good: str
    """The conforming rewrite the agent should transfer to its code."""
    note: str = ""
    """What distinguishes the pair, or how to generalize beyond it."""


class RuleDoc(NamedTuple):
    name: str
    """The rule's kebab-case slug, echoing its check function."""
    summary: str
    """One line stating what the rule requires."""
    rationale: str = ""
    """Why the rule holds, so a fix generalizes rather than papers over."""
    examples: tuple[Example, ...] = ()
    """Before/after pairs, one per distinct cause the rule has."""
    signals: tuple[str, ...] = ()
    """For a heuristic rule, the distinct causes and their remedies."""
    reference: tuple[str, ...] = ()
    """A canonical lookup table the agent applies wholesale."""
