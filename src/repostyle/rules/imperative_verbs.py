"""RS034's imperative-verb vocabulary and conjugation.

Kept separate from the docstring-form checks in `docstrings.py`: this data
(which bare-infinitive verbs to recognize, and how each conjugates) is a
distinct "vocabulary" concern from the AST-walking check that consumes it, and
this module's own top-level `IMPERATIVE_VERB_CONJUGATIONS` needs `conjugate`
defined above it, a constraint the `_effective_conjugations` in `docstrings.py`
(which also calls `conjugate`) cannot satisfy from within the same file without
an ordering conflict.
"""

from __future__ import annotations

import re

from repostyle.rules._imperative_data import (
    _ES_CONJUGATION_SUFFIXES,
    _IRREGULAR_CONJUGATIONS,
    IMPERATIVE_VERBS,
)


def conjugate(verb: str) -> str:
    """Conjugates a bare-infinitive `verb` to third-person singular."""
    if verb in _IRREGULAR_CONJUGATIONS:
        return _IRREGULAR_CONJUGATIONS[verb]
    if verb.endswith(_ES_CONJUGATION_SUFFIXES):
        return f"{verb}es"
    if len(verb) > 1 and verb.endswith("y") and verb[-2].lower() not in "aeiou":
        return f"{verb[:-1]}ies"
    return f"{verb}s"


IMPERATIVE_VERB_CONJUGATIONS: dict[str, str] = {
    verb: conjugate(verb) for verb in IMPERATIVE_VERBS
}
IMPERATIVE_OPENING_PATTERN = re.compile(
    r"^(" + "|".join(IMPERATIVE_VERB_CONJUGATIONS) + r")\b"
)


# The `explain RS034` card's reference table: only the conjugations a reader
# cannot derive by just appending `s` (an irregular stem, or the `-es`/`-ies`
# suffix rules), so it stays a quick reference at the list's full size instead
# of repeating ~200 mechanically obvious entries. Compares each conjugation
# against the plain-suffix default rather than re-deriving the branch
# conditions of `conjugate`, so the table cannot drift from what `conjugate`
# computes.
NON_TRIVIAL_CONJUGATIONS: dict[str, str] = {
    verb: conjugated
    for verb, conjugated in IMPERATIVE_VERB_CONJUGATIONS.items()
    if conjugated != f"{verb}s"
}
