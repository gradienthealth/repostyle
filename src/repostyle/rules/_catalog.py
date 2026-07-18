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
    RS_DEEPLY_NESTED_TYPE,
    RS_DISCOURAGED_CLASS_SUFFIX,
    RS_DOC_FILL,
    RS_DOC_SUMMARY_OVERFLOW,
    RS_DOC_VALUE_SIGNAL,
    RS_DURATION_AS_TIMEDELTA,
    RS_ELEMENT_ORDER,
    RS_EQ_HASH_PAIRING,
    RS_EXCEPTION_ALIAS,
    RS_EXCESSIVE_MOCKING,
    RS_FIELD_COMMENT_AS_DOCSTRING,
    RS_FILENAME_CONVENTION,
    RS_FILLER_DOCSTRING_OPENING,
    RS_GLUED_CODE_SPAN,
    RS_IMPERATIVE_DOCSTRING_OPENING,
    RS_LOWERCASE_ENTRY_DESCRIPTION,
    RS_NO_ATTRIBUTES_BLOCK,
    RS_NO_DOUBLE_BACKTICKS,
    RS_NO_MAKE_IN_PRODUCTION,
    RS_NO_MOCK_PATCH,
    RS_NO_NEGATED_BOOLEAN,
    RS_NO_PHI_SAFE_EXC_INFO,
    RS_PORT_NO_IMPLEMENTATION,
    RS_PREDICATE_FUNCTION_NAMING,
    RS_PRIVATE_IMPORT,
    RS_RAISE_DESCRIBED_IN_PROSE,
    RS_RAISES_SECTION_INCOMPLETE,
    RS_RANGE_LEN_REINDEX,
    RS_RETURN_DESCRIBED_IN_PROSE,
    RS_SHOULD_BE_PRIVATE,
    RS_SLEEPY_TEST,
    RS_SUMMARY_COMMENT_AS_DOCSTRING,
    RS_TAG_COMMENT_CONTINUATION_INDENT,
    RS_TEMPORAL_MARKER,
    RS_TERMINAL_PUNCTUATION,
    RS_TEST_NAMING,
    RS_TOO_MANY_POSITIONAL_ARGS,
    RS_UNBACKTICKED_CODE_REFERENCE,
    RS_UNBACKTICKED_SIBLING_SYMBOL,
)
from repostyle.rules.imperative_verbs import NON_TRIVIAL_CONJUGATIONS


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


# `res` and `resp` are each ambiguous; the map picks the reading that recurs:
# `res` to `result`, `resp` to `response`. The keys are exactly the banned set
# in `naming.BANNED_ABBREVIATIONS`, which a test pins so the card never drifts
# from what the rule rejects.
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
            "contract descriptively, in the third person; do not narrate its "
            "mechanics."
        ),
        signals=(
            "No docstring on a complex or many-argumented function: add a "
            "descriptive summary of its contract.",
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
    RS_TAG_COMMENT_CONTINUATION_INDENT: RuleDoc(
        name="tag-comment-continuation-indent",
        summary=(
            "A wrapped tag comment indents its continuation past the tag; a "
            "separate note is set off by a blank line."
        ),
        rationale=(
            "A `TODO(TICKET): ...` comment that wraps onto a further line reads "
            "as one unit only when the wrapped text is indented past the tag. A "
            "flush follow-on line is ambiguous: it could be the wrap or an "
            "unrelated comment. The convention resolves it by column — a "
            "continuation is indented, an independent comment is set off by a "
            "blank line. A follow-on line that is itself a tag comment is a new "
            "tag, not a wrap, and is left alone. The check spans Python, TOML, "
            "and YAML comments."
        ),
        examples=(
            Example(
                bad=(
                    "# TODO(PROC-1234): rework the retry path\n"
                    "# once the client exposes a deadline"
                ),
                good=(
                    "# TODO(PROC-1234): rework the retry path\n"
                    "#     once the client exposes a deadline"
                ),
                note="A blank line instead makes the second line its own comment.",
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
    RS_RETURN_DESCRIBED_IN_PROSE: RuleDoc(
        name="return-described-in-prose",
        summary=(
            "The return value goes in a `Returns:` section, not narrated in the "
            "docstring body."
        ),
    ),
    RS_FILENAME_CONVENTION: RuleDoc(
        name="filename-convention",
        summary=(
            "A non-Python file uses the configured preferred extension and "
            "casing (default: `.yaml` over `.yml`, kebab-case)."
        ),
        rationale=(
            "yaml.org has recommended `.yaml` since 2006; `.yml` only "
            "persists from the old DOS/Windows 8.3 filename-length limit. "
            "Google's developer documentation style guide prefers hyphens "
            "over underscores in filenames, since a search engine reads a "
            "hyphen as a word break but not an underscore. Both defaults are "
            "configurable — `[tool.repostyle.filename-extensions]` replaces "
            "the extension map wholesale, `filename-case` takes `snake` or "
            "`none`. A curated set of tool- or ecosystem-mandated fixed "
            "names (`README.md`, `CHANGELOG.md`, `LICENSE`, `CODEOWNERS`, "
            "`CLAUDE.md`, ...) is exempt from both checks by default, so a "
            "repo never re-lists them; `filename-ignore` extends that set "
            "with any further fixed-name file a tool mandates rather than "
            "renaming it. An "
            "extensionless name like `Dockerfile` or `LICENSE` only reaches "
            "this rule if the consuming repo's own pre-commit hook is "
            "configured to pass it — the shipped hook and a bare directory "
            "argument both discover only `.py`/`.toml`/`.yaml`/`.yml`/`.md`."
        ),
        examples=(
            Example(
                bad="config.yml",
                good="config.yaml",
                note="The default `filename-extensions` mapping.",
            ),
            Example(
                bad="my_config.yaml",
                good="my-config.yaml",
                note="The default `filename-case` of kebab.",
            ),
        ),
    ),
    RS_IMPERATIVE_DOCSTRING_OPENING: RuleDoc(
        name="imperative-docstring-opening",
        summary=(
            "A docstring summary opens descriptively (`Returns the lease.`), "
            "not imperatively (`Return the lease.`)."
        ),
        rationale=(
            "The house convention states a unit's contract in descriptive "
            "third person, matching Google's own style guide rather than "
            "PEP 257's imperative recommendation. The check matches a fixed "
            "set of common bare-infinitive openings adapted from "
            "pydocstyle's own word list (the data behind ruff's D401, which "
            "enforces the opposite convention), so it is advisory in both "
            "directions: an opening verb outside that set is not flagged, "
            "and a verb that commonly doubles as a noun (`Check`, `Report`, "
            "`Format`, `Handle`, `Set`, ...) still stays in the set because "
            "pydocstyle's own data accepts that risk wholesale, reinforced "
            "for several of these by a survey of real gradienthealth repos "
            "that found a genuine imperative opening for each and no "
            "noun-phrase false positive; the occasional false positive "
            "(`Check constraint enforced on the age column.`) is an "
            "accepted cost. `Route` carries the same risk on that survey's "
            "evidence alone, since it is not itself a pydocstyle entry. A "
            "handful of pydocstyle's own entries (`List`, `Query`, `Test`, "
            "...) are left out anyway because the noun reading dominates in "
            "this codebase's own domain. A consuming repo tunes the set for "
            "its own domain via `imperative-verbs-extra`/"
            "`imperative-verbs-exclude` in `[tool.repostyle]`, rather than "
            "editing the shared verb list every repo inherits."
        ),
        examples=(
            Example(
                bad='"""Return the lease held by `client_id`."""',
                good='"""Returns the lease held by `client_id`."""',
                note="Conjugate the opening verb to third-person singular.",
            ),
        ),
        reference=tuple(
            f"{verb} -> {conjugated}"
            for verb, conjugated in sorted(NON_TRIVIAL_CONJUGATIONS.items())
        ),
    ),
    RS_DOC_SUMMARY_OVERFLOW: RuleDoc(
        name="doc-summary-overflow",
        summary="A docstring summary line fills within 79 columns.",
        rationale=(
            "PEP 257 and Google style require a docstring summary to be "
            "exactly one physical line, so unlike a body paragraph it has no "
            "second line to spread overflow onto — `doc-fill`'s `--fix` "
            "cannot rewrap it, only shrink or relocate the words by hand. "
            "Move a detail that does not fit into the body or an `Args:`/"
            "`Returns:` section instead of letting the summary run long."
        ),
        examples=(
            Example(
                bad=(
                    '"""Builds the outbound claim payload from the encounter, the '
                    'coverage, and the billing provider."""'
                ),
                good=(
                    '"""Builds the outbound claim payload.\n\n'
                    "    Builds the payload from the encounter, the coverage, and\n"
                    '    the billing provider.\n    """'
                ),
                note=(
                    "Keep the summary to one short line and move the rest into "
                    "a body paragraph, which `doc-fill` can wrap."
                ),
            ),
        ),
    ),
    RS_UNBACKTICKED_CODE_REFERENCE: RuleDoc(
        name="unbackticked-code-reference",
        summary=(
            "A docstring wraps a code name it references — a parameter, an "
            "import, a class, `None`/`True`/`False` — in single backticks."
        ),
        rationale=(
            "The house style sets a code token in single backticks so prose "
            "reads apart from the identifiers it names. A linter cannot decide "
            "this for an arbitrary word, so the check stays mechanical by "
            "firing only where two signals agree: the word matches a name the "
            "module itself binds (a parameter, import, function, class, or "
            "accessed attribute) or a literal constant, and its shape rules "
            "out plain English — an underscore, a digit, or an interior "
            "capital beside a lowercase letter (`skip_lines`, `HttpClient`). A "
            "literal (`None`/`True`/`False`) fires mid-sentence but not at a "
            "sentence start, where its capital could open an English clause. A "
            "plain-lowercase name (a `path` parameter) and a Titlecase or "
            "all-caps word that also reads as English (`Path`, `WARNING`) are "
            "left to review, since no rule can tell the reference from the "
            "word. Grounding the match in the module's own names is what lets "
            "a code-shaped word the module never binds — a proper noun, or a "
            "name shown only in an example — pass untouched: the shape marks a "
            "candidate, but only a name the code defines fires."
        ),
        examples=(
            Example(
                bad='"""Returns None when skip_lines is empty."""',
                good='"""Returns `None` when `skip_lines` is empty."""',
                note=(
                    "Backtick a literal and a code-shaped parameter; a plain "
                    "word like `path` stays for review to judge."
                ),
            ),
        ),
    ),
    RS_GLUED_CODE_SPAN: RuleDoc(
        name="glued-code-span",
        summary=(
            "Prose ends a code span on a word boundary; no suffix is glued to "
            "the closing backtick."
        ),
        rationale=(
            "A code span sets a name in code font, so a suffix run straight "
            "onto its closing backtick — a possessive, a plural, or a verb "
            "ending — reads as part of the identifier and breaks the span in "
            "rendered Markdown. Moving the suffix outside the span keeps the "
            "prose readable and the identifier exact. The check stays "
            "mechanical: it fires on a closing backtick followed by a letter "
            "or an apostrophe, and leaves a hyphenated compound (`-typed`, "
            "`-safe`) alone, since that still ends the span on a word boundary."
        ),
        examples=(
            Example(
                bad='"""Returns the `Observation`s in the bundle."""',
                good='"""Returns the `Observation` resources in the bundle."""',
                note=(
                    "A possessive glues the same way: write the value of "
                    "`patient.identifier`, not `patient.identifier`'s value."
                ),
            ),
        ),
    ),
    RS_UNBACKTICKED_SIBLING_SYMBOL: RuleDoc(
        name="unbackticked-sibling-symbol",
        summary=(
            "When a docstring or comment block backticks one code symbol, its "
            "sibling code tokens in the same block are backticked too."
        ),
        rationale=(
            "Once a docstring or comment block sets one code symbol in single "
            "backticks, leaving a sibling token bare reads as an oversight, not "
            "a choice, so the house style asks for the whole block to be "
            "consistent. This check fires only on that inconsistency, which "
            "keeps it mechanical: a block must already backtick at least one "
            "code-shaped token before a bare token in it is weighed. A bare "
            "token qualifies only when its shape rules out plain English — an "
            "underscore, a digit, or an interior capital beside a lowercase "
            "letter — and when the same file carries it verbatim inside a "
            "string literal, such as a table or column name in an embedded SQL "
            "statement, which is self-contained proof it names a real "
            "identifier. A name the module binds is left to RS036, which fires "
            "on it whether or not a sibling is backticked, so the two rules "
            "never flag one token. Only Python is scanned, since the "
            "string-literal proof is read from the file's own AST."
        ),
        examples=(
            Example(
                bad=(
                    '"""`ContinuousDiscoverySettings` rejects a value, so a '
                    'remote_aes row fails to load."""'
                ),
                good=(
                    '"""`ContinuousDiscoverySettings` rejects a value, so a '
                    '`remote_aes` row fails to load."""'
                ),
                note=(
                    "`remote_aes` also appears in a SQL string elsewhere in the "
                    "file, so its bare mention beside the backticked "
                    "`ContinuousDiscoverySettings` is flagged."
                ),
            ),
        ),
    ),
    RS_DEEPLY_NESTED_TYPE: RuleDoc(
        name="deeply-nested-type",
        summary=(
            "A type annotation nests subscripted generics past two levels; name "
            "the buried type."
        ),
        rationale=(
            "A generic nested two deep inside others packs a data structure "
            "into a signature the reader re-parses at every use, and the deeper "
            "it goes the more it hides what the value actually models. Past two "
            "levels the annotation is usually standing in for a type that wants "
            "a name. A two-level `Iterator[tuple[...]]` or `dict[str, "
            "list[...]]` is idiomatic and left alone; every subscript layer "
            "beyond that counts the same — a `tuple` or a `Callable` is no "
            "easier to read nested — so the remedy is to give the inner "
            "shape a name, not to reformat the annotation. Reach for the "
            "construct that fits what the shape is: a `TypeAlias` when it is "
            "genuinely just an alias, a `NamedTuple` or dataclass when the "
            "fields deserve names."
        ),
        examples=(
            Example(
                bad="def group(rows: list[tuple[str, list[Record]]]) -> None: ...",
                good=(
                    "KeyedRecords: TypeAlias = tuple[str, list[Record]]\n"
                    "def group(rows: list[KeyedRecords]) -> None: ..."
                ),
                note=(
                    "Naming the inner `tuple[str, list[Record]]` drops the "
                    "annotation to one level and states what it holds."
                ),
            ),
        ),
    ),
    RS_RAISE_DESCRIBED_IN_PROSE: RuleDoc(
        name="raise-described-in-prose",
        summary=(
            "A raised exception goes in a `Raises:` section, not narrated in "
            "the docstring body."
        ),
    ),
    RS_EQ_HASH_PAIRING: RuleDoc(
        name="eq-hash-pairing",
        summary=("A class defines `__eq__` and `__hash__` as a pair, or neither."),
        rationale=(
            "Overriding `__eq__` without `__hash__` makes instances silently "
            "unhashable, since Python sets the class's `__hash__` to `None`; "
            "defining `__hash__` without `__eq__` keeps a value hash beside "
            "identity equality. Define both so equality and hashing agree, or "
            "set `__hash__ = None` to opt out of hashing on purpose. A "
            "`@dataclass` or `attrs` class synthesizes both and is exempt, as "
            "is a class inheriting the other half from a non-`object` base. The "
            "eq-without-hash half stands in for ruff's `PLW1641`, which is "
            "preview-gated in the pinned ruff version; when it graduates to "
            "stable, select it in `ruff-base.toml` and drop that half here."
        ),
        examples=(
            Example(
                bad="class Money:\n    def __eq__(self, other): ...",
                good=(
                    "class Money:\n"
                    "    def __eq__(self, other): ...\n"
                    "    def __hash__(self): ..."
                ),
                note=(
                    "Or make it a `@dataclass`, which synthesizes both from its "
                    "`eq=`/`frozen=` flags."
                ),
            ),
        ),
    ),
    RS_RAISES_SECTION_INCOMPLETE: RuleDoc(
        name="raises-section-incomplete",
        summary=("A `Raises:` section lists every exception the body raises outright."),
        rationale=(
            "Once a function documents its exceptions in a `Raises:` section, a "
            "reader trusts the section to be complete, so an exception the body "
            "raises with an explicit `raise SomeError(...)` but the section "
            "omits silently understates the contract. A function with no "
            "`Raises:` section does not fire — whether to document exceptions at "
            "all is the prose-side choice RS041 governs. Where an exception is "
            "both raised in code and narrated in the body, RS041 owns it and "
            "this rule stays silent."
        ),
    ),
    RS_PREDICATE_FUNCTION_NAMING: RuleDoc(
        name="predicate-function-naming",
        summary=(
            "A `-> bool` function named as a bare state word reads as a yes/no "
            "question (`is_valid`, not `valid`)."
        ),
        rationale=(
            "A boolean function should read as the question its call site asks, "
            "so a single bare adjective or state noun (`valid`, `ready`, "
            "`enabled`) takes a predicate prefix (`is_`/`has_`/`can_`/"
            "`should_`). The check is deliberately narrow to stay near "
            "zero-false-positive: it fires only on a single-word name, since a "
            "multi-word name already carries a predicate somewhere "
            "(`field_has_docstring`), and it accepts a third-person verb "
            "(`matches`, `suppresses`), the idiomatic predicate-verb name a "
            "`-> bool` function may take. A dunder, a property setter, and an "
            "`@override`/`@overload` are exempt."
        ),
        examples=(
            Example(
                bad="def valid(self) -> bool: ...",
                good="def is_valid(self) -> bool: ...",
                note="A predicate verb (`matches`, `exists`) needs no prefix.",
            ),
        ),
    ),
    RS_TEMPORAL_MARKER: RuleDoc(
        name="temporal-marker",
        summary=(
            "A docstring or comment states the code's present contract, not a "
            "temporal or edit-narrative marker of how it changed."
        ),
        rationale=(
            "A durable docstring or comment describes what the code does now. A "
            "marker like `previously`, `used to`, `formerly`, `originally`, `as "
            "discussed`, `we decided`, `for now`, `changed to`, or `switched "
            "to` narrates the edit or the design discussion instead — the story "
            "belongs in the commit message, where it stays attached to the "
            "diff, not in prose a later reader mistakes for the current "
            "contract. This is the common shape of an agent leaking the "
            "session's design chat into the code. The set is held deliberately "
            "tight (ambiguous words like `currently`, `instead of`, or `note "
            "that` are left out) and a marker quoted in a backtick span is "
            "read as data, not narration, so the rule stays a mechanical floor. "
            "The judgment ceiling — prose that narrates the edit without one of "
            "these exact markers — is the `common-style-review` prose-economy "
            "lens this rule is synced with. Not auto-fixable: cutting the "
            "narration cleanly needs judgment, so no `--fix`."
        ),
        examples=(
            Example(
                bad='"""Returns the lease. Previously returned a raw dict."""',
                good='"""Returns the lease."""',
                note="Drop the note on the old shape; the diff already records it.",
            ),
            Example(
                bad="# we decided to cache this for now",
                good="# cached because the upstream call dominates the request time",
                note=(
                    "Replace the decision narration with the durable reason the "
                    "code is the way it is, or delete the comment."
                ),
            ),
        ),
    ),
    RS_RANGE_LEN_REINDEX: RuleDoc(
        name="range-len-reindex",
        summary=(
            "A `for i in range(len(seq))` that only indexes `seq[i]` should "
            "iterate `seq` directly."
        ),
        rationale=(
            "Looping over `range(len(seq))` to read `seq[i]` at each step spends "
            "an index variable on what `for item in seq:` says directly, and the "
            "indirection hides that the loop is a plain traversal. The check "
            "fires only when the index is used for nothing but subscripting that "
            "same sequence, so a loop that also needs the index — for "
            "arithmetic, a second sequence, or a call — is left alone rather "
            "than steered toward `enumerate`, the weaker suggestion this rule "
            "deliberately does not make. No stable ruff rule expresses this: "
            "pylint's `C0200` (`consider-using-enumerate`) covers the shape but "
            "is not ported to ruff's rule set, so it stays a genuine gap this "
            "rule fills."
        ),
        examples=(
            Example(
                bad="for i in range(len(rows)):\n    process(rows[i])",
                good="for row in rows:\n    process(row)",
                note=(
                    "When the index is needed too — `rows[i]` beside `i + 1` or "
                    "a bare `i` — the loop is left alone."
                ),
            ),
        ),
    ),
    RS_LOWERCASE_ENTRY_DESCRIPTION: RuleDoc(
        name="lowercase-entry-description",
        summary=(
            "An `Args:`/`Returns:`/`Raises:`/`Yields:` entry description opens "
            "with a capital letter (`bar: A bar.`, not `bar: a bar.`)."
        ),
        rationale=(
            "The house treats each Google-section entry description as a full "
            "sentence, so it opens with a capital just as RS030 requires it to "
            "close with a period — the two rules are the opening-capital and "
            "closing-period halves of one convention. ChromiumOS's Python style "
            "guide requires docstring content, including argument descriptions, "
            "to be full sentences with proper capitalization and punctuation, "
            "and Google's own `Args:` examples are capitalized. No ruff or "
            "pydocstyle rule enforces entry-description capitalization, so it is "
            "a genuine gap. The check stays near zero-false-positive: only a "
            "lowercase ASCII prose letter fires, and a description opening with "
            "a backtick code span, an inherently-lowercase code token (a "
            "parameter name or a dotted path like `json.dumps`), a digit, or any "
            "other non-letter is left alone."
        ),
        examples=(
            Example(
                bad="Args:\n    bar: a bar.",
                good="Args:\n    bar: A bar.",
            ),
            Example(
                bad="Raises:\n    NotFoundError: if a foo is not found.",
                good="Raises:\n    NotFoundError: If a foo is not found.",
            ),
        ),
    ),
    RS_PRIVATE_IMPORT: RuleDoc(
        name="private-import",
        summary=(
            "A first-party import consumes another package's public surface, "
            "not its `_`-private internals."
        ),
        rationale=(
            "A single leading underscore marks a module or name internal to the "
            "package that holds it, so reaching it from outside that package "
            "relies on an implementation detail the author did not publish. The "
            "supported way to use another package is the surface it re-exports "
            "from its `__init__`; if a member is needed there, it should be "
            "lifted onto that surface, not reached past. This is the dual of "
            "RS029: RS029 asks a package to hide what only it uses, this asks "
            "other code not to reach into what was hidden. The check scopes to "
            "imports that share the importer's top-level package, so it governs "
            "a repo's own layering and leaves a reach into a third-party "
            "distribution — whose internals a repo cannot restructure — alone. "
            "It follows PEP 8's `Public and internal interfaces`: an interface "
            "is internal if any containing namespace is, and other modules must "
            "not rely on indirect access to it except through a package's "
            "documented `__init__`. A test module is exempt, since exercising a "
            "unit under test's internals is expected."
        ),
        examples=(
            Example(
                bad="# in myapp/api/views.py\nfrom myapp.core._engine import run",
                good="# in myapp/api/views.py\nfrom myapp.core import run",
                note=(
                    "`_engine` is internal to `myapp.core`, and `views` lives "
                    "outside `core`, so it must go through `core`'s public "
                    "surface. Re-export `run` from `core/__init__.py` rather "
                    "than reaching past it. An import from within `myapp.core` "
                    "itself is fine."
                ),
            ),
        ),
    ),
}


def rule_doc(rule_id: str) -> RuleDoc | None:
    """Returns a rule's metadata record, or `None` for an unknown id."""
    return RULE_DOCS.get(rule_id)


def has_guidance(rule_id: str) -> bool:
    """Reports whether a rule carries detail past its one-line summary.

    True when the rule has examples, heuristic signals, or a reference table —
    the rules whose card is worth fetching, so the discovery hint points only
    at those.
    """
    doc = RULE_DOCS.get(rule_id)
    return doc is not None and bool(doc.examples or doc.signals or doc.reference)
