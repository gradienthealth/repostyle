"""Render a rule's metadata record into an agent-facing explanation card.

The `explain` subcommand and the discovery hint both render from the
`RuleDoc` catalog here, so the rich surfaces stay one source. The card
is plain text wrapped to 72 columns, the width the house style fills
prose to, with example code left unwrapped so it can be copied verbatim.
"""

from __future__ import annotations

import textwrap

from repostyle.rules import (
    DOC_FILL_COLUMNS,
    FIXABLE_RULES,
    Example,
    RuleDoc,
    rule_doc,
    severity_of,
)

_WIDTH = DOC_FILL_COLUMNS
_INDENT = "  "
_CODE_INDENT = "      "


def explain_rule(rule_id: str) -> str | None:
    """Render a rule's full explanation card, or None for an unknown id."""
    doc = rule_doc(rule_id)
    if doc is None:
        return None
    return _render_card(rule_id, doc)


def discovery_hint(rule_id: str) -> str:
    """Return the one-line pointer to a rule's card for the failure stream."""
    return f"→ run 'repostyle explain {rule_id}' for guidance and examples"


def _render_card(rule_id: str, doc: RuleDoc) -> str:
    """Assemble a rule's card from its metadata record."""
    severity = severity_of(rule_id).value
    blocks = [f"{rule_id}  {doc.name}  ({severity})", _wrap(doc.summary)]
    if doc.rationale:
        blocks.append("Why:\n" + _wrap(doc.rationale))
    if doc.signals:
        blocks.append("Likely causes and remedies:\n" + _bullets(doc.signals))
    if doc.examples:
        blocks.append("Examples:\n" + _examples(doc.examples))
    if doc.reference:
        blocks.append("Reference:\n" + _bullets(doc.reference))
    blocks.append(_fixable_line(rule_id))
    return "\n\n".join(blocks)


def _bullets(items: tuple[str, ...]) -> str:
    """Wrap each item as a hanging-indented bullet."""
    return "\n".join(
        textwrap.fill(
            item,
            width=_WIDTH,
            initial_indent=f"{_INDENT}- ",
            subsequent_indent=f"{_INDENT}  ",
        )
        for item in items
    )


def _examples(examples: tuple[Example, ...]) -> str:
    """Render each before/after pair, leaving its code unwrapped."""
    rendered: list[str] = []
    for example in examples:
        parts = [
            f"{_INDENT}bad:",
            _code(example.bad),
            f"{_INDENT}good:",
            _code(example.good),
        ]
        if example.note:
            parts.append(
                textwrap.fill(
                    f"note: {example.note}",
                    width=_WIDTH,
                    initial_indent=_INDENT,
                    subsequent_indent=f"{_INDENT}  ",
                )
            )
        rendered.append("\n".join(parts))
    return "\n".join(rendered)


def _code(snippet: str) -> str:
    """Indent a code snippet's lines so it reads as a verbatim block."""
    return "\n".join(f"{_CODE_INDENT}{line}" for line in snippet.splitlines())


def _fixable_line(rule_id: str) -> str:
    """State whether the rule is autofixable, and how."""
    if rule_id in FIXABLE_RULES:
        return "Fixable: yes — rerun with `repostyle --fix`."
    return "Fixable: no."


def _wrap(text: str) -> str:
    """Fill prose to the house width under the standard indent."""
    return textwrap.fill(
        text, width=_WIDTH, initial_indent=_INDENT, subsequent_indent=_INDENT
    )


__all__ = ["discovery_hint", "explain_rule"]
