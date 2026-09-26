"""A partition of the rule explanation catalog."""

from repostyle.rules._catalog_types import Example, RuleDoc
from repostyle.rules._violation import (
    RS_BANNED_IMPORT_BY_PATH,
    RS_COMMENT_TAG_FORMAT,
    RS_DOC_VALUE_SIGNAL,
    RS_ELEMENT_ORDER,
    RS_FIELD_COMMENT_AS_DOCSTRING,
    RS_FILLER_DOCSTRING_OPENING,
    RS_NO_NEGATED_BOOLEAN,
    RS_SOURCE_MODULE_SIZE,
    RS_SUMMARY_COMMENT_AS_DOCSTRING,
    RS_TAG_COMMENT_CONTINUATION_INDENT,
    RS_TEST_MODULE_SIZE,
)

RULE_DOCS_PART: dict[str, RuleDoc] = {
    RS_TEST_MODULE_SIZE: RuleDoc(
        name="test-module-size",
        summary=("A test module stays within its configured physical code-line limit."),
        rationale=(
            "A large test module can expose a production unit with too many "
            "responsibilities, or it can collect unrelated behavior in one "
            "place. Review the production boundary first. When that boundary "
            "is cohesive, split the tests by behavior into modules with names "
            "that state what each covers. Do not create numbered fragments or "
            "remove coverage merely to cross the threshold. The default limit "
            "is 500, configured with `max-test-file-lines` in "
            "`[tool.repostyle]`."
        ),
        signals=(
            "Tests span unrelated production responsibilities: split or "
            "simplify the production unit, then align test modules to those "
            "boundaries.",
            "The production boundary is cohesive but its behavior has distinct "
            "areas: organize tests into named modules around those areas.",
            "The module must stay intact for a documented reason: place "
            "`# style: ignore-file[RS062]` near the top with a short rationale.",
        ),
    ),
    RS_SOURCE_MODULE_SIZE: RuleDoc(
        name="source-module-size",
        summary=(
            "A Python source module stays within its configured physical "
            "code-line limit."
        ),
        rationale=(
            "A large source module can hide several responsibilities behind "
            "one import boundary. Find the distinct concepts or workflows and "
            "give each a cohesive module with a name that describes what it "
            "owns. Do not move unrelated leftovers into a generic utility "
            "module or split one responsibility into numbered fragments merely "
            "to cross the threshold. The default limit is 250, configured with "
            "`max-source-file-lines` in `[tool.repostyle]`."
        ),
        signals=(
            "The module owns distinct concepts or workflows: split them along "
            "those responsibility boundaries.",
            "The module is one cohesive responsibility with substantial data "
            "or declarations: keep the structure readable and use a targeted "
            "waiver when a split would obscure ownership.",
            "The module must stay intact for a documented reason: place "
            "`# style: ignore-file[RS066]` near the top with a short rationale.",
        ),
    ),
    RS_BANNED_IMPORT_BY_PATH: RuleDoc(
        name="banned-import-by-path",
        summary="A file imports a module its layer's `banned-imports` config forbids.",
        rationale=(
            "The bans express the repo's layering boundaries -- an inner domain "
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
            "unrelated comment. The convention resolves it by column -- a "
            "continuation is indented, an independent comment is set off by a "
            "blank line. A follow-on line that is itself a tag comment is a new "
            "tag, not a wrap, and is left alone. The check spans Python, TOML, "
            "YAML, and shell comments."
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
}
