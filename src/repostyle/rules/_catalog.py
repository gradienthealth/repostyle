"""Agent-facing rule metadata: the source every rich explanation renders from.

The one-line finding a rule emits tells a consumer what tripped, not how to fix
it or how to generalize the fix to lines the linter never flagged. That
guidance lives in the rule docstrings, where a consuming repo's agent cannot
reach it. This module lifts it into structured data — a `RuleDoc` per rule — so
the `explain` subcommand and any later format render from one source rather
than parsing prose back out of docstrings.

Every rule carries a `summary`; the rules where general knowledge falls short —
config-driven bans, heuristic warnings with no single fix — carry richer
`rationale`, `examples`, `signals`, or a `reference` table. A rule whose
one-line message already tells a competent agent the fix is left at its summary
on purpose, to keep the cards worth reading.
"""

from __future__ import annotations

from typing import NamedTuple

from repostyle.rules._violation import (
    RS_ACRONYM_CASING,
    RS_ARG_DESCRIBED_IN_PROSE,
    RS_BANNED_ABBREVIATION,
    RS_BANNED_IMPORT_BY_PATH,
    RS_BEHAVIOR_VERIFICATION_ONLY,
    RS_BOOLEAN_PREFIX_REQUIRED,
    RS_COGNITIVE_COMPLEXITY,
    RS_COMMENT_TAG_FORMAT,
    RS_CONDITIONAL_TEST_LOGIC,
    RS_DISCOURAGED_CLASS_SUFFIX,
    RS_DOC_FILL,
    RS_DOC_VALUE_SIGNAL,
    RS_DURATION_AS_TIMEDELTA,
    RS_ELEMENT_ORDER,
    RS_EXCEPTION_ALIAS,
    RS_EXCESSIVE_MOCKING,
    RS_FIELD_COMMENT_AS_DOCSTRING,
    RS_FILLER_DOCSTRING_OPENING,
    RS_NO_ATTRIBUTES_BLOCK,
    RS_NO_DOUBLE_BACKTICKS,
    RS_NO_MAKE_IN_PRODUCTION,
    RS_NO_MOCK_PATCH,
    RS_NO_NEGATED_BOOLEAN,
    RS_NO_PHI_SAFE_EXC_INFO,
    RS_PORT_NO_IMPLEMENTATION,
    RS_SHOULD_BE_PRIVATE,
    RS_SLEEPY_TEST,
    RS_SUMMARY_COMMENT_AS_DOCSTRING,
    RS_TERMINAL_PUNCTUATION,
    RS_TEST_NAMING,
    RS_TOO_MANY_POSITIONAL_ARGS,
)


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


# `res` and `resp` both abbreviate response-shaped names; `res` is left to
# `result` and `resp` to `response`, the two readings that recur. The keys are
# exactly the banned set in `naming.BANNED_ABBREVIATIONS`, which a test pins so
# the card never drifts from what the rule rejects.
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


RULE_DOCS: dict[str, RuleDoc] = {
    RS_ACRONYM_CASING: RuleDoc(
        name="acronym-casing",
        summary=(
            "A known acronym stays all-uppercase in a CapWords name "
            "(`FHIRClient`, not `FhirClient`)."
        ),
    ),
    RS_TEST_NAMING: RuleDoc(
        name="test-naming",
        summary=(
            "A test under `tests/unit/` matches `test_StateUnderTest_ExpectedBehavior`."
        ),
    ),
    RS_NO_MOCK_PATCH: RuleDoc(
        name="no-mock-patch",
        summary=(
            "`unittest.mock` and `mock` are rejected outside `tests/fakes/`; "
            "use a port fake."
        ),
    ),
    RS_NO_ATTRIBUTES_BLOCK: RuleDoc(
        name="no-attributes-block",
        summary=(
            "A dataclass documents fields with per-field docstrings, not a "
            "Google `Attributes:` block."
        ),
    ),
    RS_NO_DOUBLE_BACKTICKS: RuleDoc(
        name="no-double-backticks",
        summary="Prose uses single backticks for a code span, never double.",
    ),
    RS_PORT_NO_IMPLEMENTATION: RuleDoc(
        name="port-no-implementation",
        summary="A port module declares contracts only; it holds no implementation.",
    ),
    RS_DURATION_AS_TIMEDELTA: RuleDoc(
        name="duration-as-timedelta",
        summary=(
            "A module-level duration is a `timedelta`, not a raw `*_SECONDS` number."
        ),
    ),
    RS_NO_PHI_SAFE_EXC_INFO: RuleDoc(
        name="no-phi-safe-exc-info",
        summary=(
            "A PHI-safe logger call passes no `exc_info`; a traceback can carry "
            "PHI past the redaction."
        ),
    ),
    RS_DOC_FILL: RuleDoc(
        name="doc-fill",
        summary="A docstring or comment paragraph fills to 79 columns.",
        rationale=(
            "A paragraph wrapped well short of the limit, or running past it, "
            "reads as ragged and churns diffs when reflowed by hand. Fill each "
            "prose paragraph to 79 columns. Docstrings are checked in Python; "
            "comments in Python, TOML, and YAML alike. `--fix` rewrites Python "
            "in place."
        ),
    ),
    RS_BANNED_ABBREVIATION: RuleDoc(
        name="banned-abbreviation",
        summary=(
            "Spell names out; a known abbreviation in an introduced name is rejected."
        ),
        rationale=(
            "An abbreviation saves a few characters at the cost of a reader "
            "expanding it, and the expansions disagree across a codebase (`req` "
            "for request, requirement, or required). Spelling the word out keeps "
            "names searchable and unambiguous. The abbreviation is matched as a "
            "whole word in a snake_case or CapWords name, so an attribute access "
            "or a string literal is left alone."
        ),
        examples=(
            Example(
                bad="def handle(req, resp): ...",
                good="def handle(request, response): ...",
                note=(
                    "Fix every abbreviation in the file, not just the flagged "
                    "one — the reference below is the full banned set."
                ),
            ),
        ),
        reference=tuple(
            f"{abbreviation} -> {expansion}"
            for abbreviation, expansion in sorted(ABBREVIATION_EXPANSIONS.items())
        ),
    ),
    RS_DISCOURAGED_CLASS_SUFFIX: RuleDoc(
        name="discouraged-class-suffix",
        summary=(
            "A class is named for its responsibility, not a vague "
            "`Manager`/`Helper`/`Util` role."
        ),
    ),
    RS_COGNITIVE_COMPLEXITY: RuleDoc(
        name="cognitive-complexity",
        summary="A function's cognitive complexity is over the limit of 15.",
        rationale=(
            "Cognitive complexity weights control flow by nesting depth, so the "
            "remedy is rarely to shorten the function — it is to flatten or "
            "factor the structure driving the score. Reach for the remedy that "
            "matches the cause, not a blanket extraction."
        ),
        signals=(
            "Deep nesting (an `if` inside a `for` inside an `if`): invert the "
            "condition and `return` or `continue` early to peel off a level, or "
            "extract the inner block into its own function.",
            "Many sibling branches (a long `if`/`elif` chain): replace it with a "
            "dispatch table or a mapping keyed by the discriminant.",
            "Long boolean chains (`a and b or c and d`): extract the condition "
            "into a named predicate whose name states what it tests.",
        ),
    ),
    RS_CONDITIONAL_TEST_LOGIC: RuleDoc(
        name="conditional-test-logic",
        summary=(
            "A test keeps its asserted path straight-line, not wrapped in an "
            "`if`/`for`/`while`/`try`."
        ),
    ),
    RS_SLEEPY_TEST: RuleDoc(
        name="sleepy-test",
        summary=(
            "A test does not call `time.sleep`/`asyncio.sleep`; wait on a "
            "condition or fake the clock."
        ),
    ),
    RS_EXCESSIVE_MOCKING: RuleDoc(
        name="excessive-mocking",
        summary=(
            "A test builds more than three mocks, a density signal of brittle coupling."
        ),
        rationale=(
            "A high mock count is a signal of where to look, not a verdict that "
            "any single mock is wrong. Many mocks usually means the unit reaches "
            "across too many collaborators, or that a mock stands in where a fake "
            "would assert real behavior."
        ),
        signals=(
            "Replace a mock of your own collaborator with a port fake under "
            "`tests/fakes/` that records and replays observable interactions.",
            "If the unit needs many mocks to stand up, it may have too many "
            "dependencies — consider whether it is doing too much.",
            "A mock that only satisfies a constructor argument can often be a "
            "real lightweight value or a shared fixture.",
        ),
    ),
    RS_BEHAVIOR_VERIFICATION_ONLY: RuleDoc(
        name="behavior-verification-only",
        summary=(
            "A test asserts only call choreography (`assert_called*`), never state."
        ),
        rationale=(
            "A test whose only checks are `assert_called*` pins how the unit "
            "calls its collaborators rather than the outcome a caller relies on, "
            "so it passes a buggy refactor that preserves the calls and fails a "
            "correct one that changes them. Assert the observable result and let "
            "the calls be an implementation detail."
        ),
        examples=(
            Example(
                bad=(
                    "repository.save(patient)\n"
                    "repository.save.assert_called_once_with(patient)"
                ),
                good="repository.save(patient)\nassert repository.stored == [patient]",
                note="Assert the fake's recorded state, not that a method was called.",
            ),
        ),
    ),
    RS_BANNED_IMPORT_BY_PATH: RuleDoc(
        name="banned-import-by-path",
        summary="A file imports a module its layer's `banned-imports` config forbids.",
        rationale=(
            "The bans express the repo's layering boundaries — an inner domain "
            "or port module must not import an outer adapter or the CLI, so the "
            "dependency arrow points inward. The fix is not to delete the import "
            "but to move the code that needs it to the layer that may hold it, or "
            "to invert the dependency behind a port the inner layer owns. The "
            "banned sources are configured per glob in "
            "`[tool.repostyle.banned-imports]`; read that table for which layer "
            "owns what."
        ),
        examples=(
            Example(
                bad=(
                    "# in src/domain/ports/clock.py\n"
                    "from myrepo.adapters.system_clock import now"
                ),
                good=(
                    "# the port declares the contract; an adapter implements it\n"
                    "class Clock(Protocol):\n"
                    "    def now(self) -> datetime: ..."
                ),
                note=(
                    "Depend on an abstraction the inner layer owns; let the "
                    "outer layer provide the concrete import."
                ),
            ),
        ),
    ),
    RS_DOC_VALUE_SIGNAL: RuleDoc(
        name="doc-value-signal",
        summary=(
            "A non-trivial public function is under-documented (no docstring, or "
            "a tuple return with no `Returns:`)."
        ),
        rationale=(
            "The rule fires only where a docstring earns its keep, so the fix is "
            "a real docstring, not boilerplate. State the function's own "
            "contract in the imperative; do not narrate its mechanics."
        ),
        signals=(
            "No docstring on a complex or many-argumented function: add an "
            "imperative summary of its contract.",
            "A multi-element tuple return: add a `Returns:` section naming each "
            "element in order, which one summary line cannot.",
        ),
    ),
    RS_ELEMENT_ORDER: RuleDoc(
        name="element-order",
        summary=(
            "Module and class members run top-down by dependency, then "
            "alphabetical for free choices."
        ),
    ),
    RS_SUMMARY_COMMENT_AS_DOCSTRING: RuleDoc(
        name="summary-comment-as-docstring",
        summary="A leading summary comment on a definition should be its docstring.",
    ),
    RS_FIELD_COMMENT_AS_DOCSTRING: RuleDoc(
        name="field-comment-as-docstring",
        summary="A dataclass field's explanatory comment should be a field docstring.",
    ),
    RS_COMMENT_TAG_FORMAT: RuleDoc(
        name="comment-tag-format",
        summary=(
            "A special comment reads `TAG(TICKET): message` with an allowed tag "
            "and a tracking ticket."
        ),
        rationale=(
            "A `TODO`/`FIXME`/`NOTE`/`HACK` comment that points at a ticket "
            "stays traceable to the work that resolves it, mirroring the ticket "
            "scope a PR title carries. The form is an allowed tag, the ticket in "
            "parentheses (a Linear id like `PROC-1234`, or the literal "
            "`NO-ISSUE`), then `: ` and the message. The allowed tags and ticket "
            "pattern are configured in `[tool.repostyle]`."
        ),
        examples=(
            Example(
                bad="# TODO: handle the empty case",
                good="# TODO(PROC-1234): handle the empty case",
                note="With no ticket, use `# TODO(NO-ISSUE): ...`.",
            ),
        ),
    ),
    RS_FILLER_DOCSTRING_OPENING: RuleDoc(
        name="filler-docstring-opening",
        summary=(
            "A docstring opens with the unit's contract, not a filler phrase "
            "(`This function ...`)."
        ),
    ),
    RS_NO_NEGATED_BOOLEAN: RuleDoc(
        name="no-negated-boolean",
        summary=(
            "A boolean name does not embed `not`/`no`; name the positive and "
            "negate at the call site."
        ),
    ),
    RS_NO_MAKE_IN_PRODUCTION: RuleDoc(
        name="no-make-in-production",
        summary=(
            "`make_` is for test fixtures; production uses `build_` (in-memory) "
            "or `create_` (side effect)."
        ),
    ),
    RS_BOOLEAN_PREFIX_REQUIRED: RuleDoc(
        name="boolean-prefix-required",
        summary=(
            "A `bool`-annotated name reads as a yes/no question "
            "(`is_`/`has_`/`can_`/`should_`)."
        ),
    ),
    RS_TOO_MANY_POSITIONAL_ARGS: RuleDoc(
        name="too-many-positional-args",
        summary=(
            "A function takes few positional parameters; pass the rest as keywords."
        ),
    ),
    RS_EXCEPTION_ALIAS: RuleDoc(
        name="exception-alias",
        summary=(
            "An `except ... as` alias is `exc` (`exc2` when nested) or a "
            "descriptive name, never `e`/`ex`/`err`."
        ),
    ),
    RS_SHOULD_BE_PRIVATE: RuleDoc(
        name="should-be-private",
        summary=(
            "A symbol used only inside its own package carries a leading underscore."
        ),
    ),
    RS_TERMINAL_PUNCTUATION: RuleDoc(
        name="terminal-punctuation",
        summary=(
            "A docstring or comment prose unit ends with terminal punctuation "
            "(`.`, `!`, or `?`); comments are checked in Python, TOML, and YAML."
        ),
    ),
    RS_ARG_DESCRIBED_IN_PROSE: RuleDoc(
        name="arg-described-in-prose",
        summary=(
            "Per-argument detail goes in an `Args:` section, not narrated in the "
            "docstring body."
        ),
    ),
}


def rule_doc(rule_id: str) -> RuleDoc | None:
    """Return a rule's metadata record, or None for an unknown id."""
    return RULE_DOCS.get(rule_id)


def has_guidance(rule_id: str) -> bool:
    """Report whether a rule carries detail past its one-line summary.

    True when the rule has examples, heuristic signals, or a reference table —
    the rules whose card is worth fetching, so the discovery hint points only
    at those.
    """
    doc = RULE_DOCS.get(rule_id)
    return doc is not None and bool(doc.examples or doc.signals or doc.reference)
