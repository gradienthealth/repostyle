"""A partition of the rule explanation catalog."""

from repostyle.rules._catalog_types import ABBREVIATION_EXPANSIONS, Example, RuleDoc
from repostyle.rules._violation import (
    RS_ACRONYM_CASING,
    RS_BANNED_ABBREVIATION,
    RS_COGNITIVE_COMPLEXITY,
    RS_CONDITIONAL_TEST_LOGIC,
    RS_DISCOURAGED_CLASS_SUFFIX,
    RS_DOC_FILL,
    RS_DURATION_AS_TIMEDELTA,
    RS_NO_ATTRIBUTES_BLOCK,
    RS_NO_DOUBLE_BACKTICKS,
    RS_NO_MOCK_PATCH,
    RS_NO_PHI_SAFE_EXC_INFO,
    RS_PORT_NO_IMPLEMENTATION,
    RS_SLEEPY_TEST,
    RS_TEST_NAMING,
)

RULE_DOCS_PART: dict[str, RuleDoc] = {
    RS_ACRONYM_CASING: RuleDoc(
        name="acronym-casing",
        summary=(
            "A known acronym stays all-uppercase in a CapWords name "
            "(`FHIRClient`, not `FhirClient`)."
        ),
        rationale=(
            "The check holds a fixed set of known acronyms (`API`, `FHIR`, "
            "`HTTP`, `ID`, `JWT`, `URL`, ...) to all-uppercase in a CapWords "
            "name, since a mixed-case acronym reads as an ordinary word. The "
            "set is general, so a domain repo extends it via `acronyms-extra` "
            "and drops a member via `acronyms-exclude` in `[tool.repostyle]`, "
            "rather than editing the shared list every repo inherits."
        ),
        examples=(
            Example(
                bad="class UidValidator: ...",
                good="class UIDValidator: ...",
                note=(
                    "`UID` is not a built-in acronym; a DICOM repo teaches the "
                    'rule with `acronyms-extra = ["UID"]`.'
                ),
            ),
        ),
    ),
    RS_TEST_NAMING: RuleDoc(
        name="test-naming",
        summary=(
            "A test under `tests/unit/` (or the configured `test-naming-globs`) "
            "matches `test_StateUnderTest_ExpectedBehavior`."
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
        rationale=(
            "Scoped to files whose path holds the `application/ports/` fragment "
            "of a hexagonal layout, or to the files matching `port-path-globs` "
            "in `[tool.repostyle]` when a repo sets that key, which replaces the "
            "default fragment rather than extending it. A repo whose ports sit "
            "elsewhere states its own layout there."
        ),
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
        summary=(
            "A docstring, comment, or YAML folded-scalar paragraph fills to 79 columns."
        ),
        rationale=(
            "A paragraph wrapped well short of the limit, or running past it, "
            "reads as ragged and churns diffs when reflowed by hand. Fill each "
            "prose paragraph to 79 columns. Only prose is filled: a preformatted "
            "line -- one ending in a `\\` continuation, or holding an interior "
            "run of spaces that aligns a column -- is verbatim, since a reflow "
            "emits "
            "single-spaced text and would corrupt it. Docstrings are checked in "
            "Python; comments in Python, TOML, YAML, and shell alike. YAML "
            "prose is checked too, inside a folded (`>`) block scalar that "
            "closes on a `.`, `!`, or `?`: its line breaks fold to spaces, so a "
            "rewrap leaves the value alone, and the closing punctuation "
            "separates prose from the `>` blocks that merely wrap a long "
            "expression. A literal (`|`) scalar keeps its breaks as content and "
            "is never touched. A folded scalar that closes on anything else "
            "goes unchecked, and no rule covers it: RS030 reads `#` comments "
            "alone. Close the prose with a period and RS009 applies. `--fix` "
            "rewrites every language it reads."
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
                    "one -- the reference below is the full banned set."
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
            "remedy is rarely to shorten the function -- it is to flatten or "
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
}
