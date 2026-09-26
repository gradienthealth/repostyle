"""A partition of the rule explanation catalog."""

from repostyle.rules._catalog_types import Example, RuleDoc
from repostyle.rules._violation import (
    RS_EQ_HASH_PAIRING,
    RS_LOWERCASE_ENTRY_DESCRIPTION,
    RS_PREDICATE_FUNCTION_NAMING,
    RS_RAISES_SECTION_INCOMPLETE,
    RS_RANGE_LEN_REINDEX,
    RS_TEMPORAL_MARKER,
)

RULE_DOCS_PART: dict[str, RuleDoc] = {
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
            "`Raises:` section does not fire -- whether to document exceptions at "
            "all is the prose-side choice RS041 governs. Where an exception is "
            "both raised in code and narrated in unstructured docstring prose, "
            "RS041 owns it and this rule stays silent."
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
            "to` narrates the edit or the design discussion instead -- the story "
            "belongs in the commit message, where it stays attached to the "
            "diff, not in prose a later reader mistakes for the current "
            "contract. This is the common shape of an agent leaking the "
            "session's design chat into the code. The set is held deliberately "
            "tight (ambiguous words like `currently`, `instead of`, or `note "
            "that` are left out) and a marker quoted in a backtick span is "
            "read as data, not narration, so the rule stays a mechanical floor. "
            "The judgment ceiling -- prose that narrates the edit without one of "
            "these exact markers -- is left to review. Not auto-fixable: cutting "
            "the narration cleanly needs judgment, so no `--fix`."
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
            "same sequence, so a loop that also needs the index -- for "
            "arithmetic, a second sequence, or a call -- is left alone rather "
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
                    "When the index is needed too -- `rows[i]` beside `i + 1` or "
                    "a bare `i` -- the loop is left alone."
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
            "close with a period -- the two rules are the opening-capital and "
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
}
