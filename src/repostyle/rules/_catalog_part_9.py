"""A partition of the rule explanation catalog."""

from repostyle.rules._catalog_types import Example, RuleDoc
from repostyle.rules._violation import (
    RS_BANNER_COMMENT,
    RS_DOCSTRING_SECTION_ALIAS,
    RS_DOCSTRING_SECTION_ORDER,
    RS_DOUBLE_SPACE_AFTER_PERIOD,
    RS_DUPLICATE_DOCSTRING_SECTION,
    RS_INVALID_DOCSTRING_SECTION,
)

RULE_DOCS_PART: dict[str, RuleDoc] = {
    RS_BANNER_COMMENT: RuleDoc(
        name="banner-comment",
        summary=(
            "No banner, section-divider, or framed-title comments: the rule "
            "characters go and the grouping is expressed with structure."
        ),
        rationale=(
            "A banner -- a lone `# -----` divider, the frame lines boxing a "
            "`# TESTS` title, or a one-line `# --- main ---` -- decorates a "
            "grouping instead of expressing it, and a file reaching for "
            "visual section markers is reporting that it wants higher-level "
            "modularization. Take the alternative that fits: split the module "
            "so each section is its own file, gather the section into a class "
            "(test functions under one section into a test class), or, where "
            "the file must stay whole, open the run with a sentence comment "
            "saying what it holds. Only the typography is banned -- `# "
            "Handlers for the BigQuery MCP tool.` is an ordinary comment and "
            "passes. The set is banned outright rather than held to one "
            "canonical shape because every author picks a different width, "
            "character, casing, and closing run, so the convention never "
            "converges. The check flags a comment whose text is wholly rule "
            "characters, or that a run of three or more opens or closes "
            "against whitespace; YAML's commented-out `# ---` document "
            "separator, the `+----+` ASCII-table border, PEP 263's `-*- "
            "coding: utf-8 -*-` line, an ASCII scissors (`---8<---`), and an "
            "arrow (`----->`) stay exempt. Not auto-fixable: deleting the "
            "divider is trivial, but the restructuring it points at is not."
        ),
        examples=(
            Example(
                bad="# ----------------\n# HELPERS\n# ----------------\ndef _one(): ...",
                good="def _one(): ...",
                note=(
                    "Delete the divider; a file that genuinely has sections "
                    "wants a class or a module split, not typography."
                ),
            ),
            Example(
                bad=(
                    "# --- baseline ---\n"
                    "def test_baseline_returns_every_cohort(): ...\n\n"
                    "# --- offset ---\n"
                    "def test_offset_skips_the_leading_cohorts(): ..."
                ),
                good=(
                    "class TestBaseline:\n"
                    "    def test_returns_every_cohort(self): ...\n\n\n"
                    "class TestOffset:\n"
                    "    def test_skips_the_leading_cohorts(self): ..."
                ),
                note=(
                    "A framed title is flagged whatever its width or casing. "
                    "A test file dividing itself into sections is the "
                    "commonest case, and a test class per section names the "
                    "grouping in code."
                ),
            ),
            Example(
                bad="# ========== BigQuery MCP ==========",
                good="# Handlers for the BigQuery MCP tool.",
                note=(
                    "Where the module must stay whole, a sentence comment "
                    "carries the same grouping without the typography."
                ),
            ),
        ),
    ),
    RS_INVALID_DOCSTRING_SECTION: RuleDoc(
        name="invalid-docstring-section",
        summary=(
            "A docstring section header comes from the recognized Google set "
            "-- `Args:`, `Returns:`, `Yields:`, `Raises:`, `Note:`, "
            "`Example:` -- not an invented or Sphinx-imported one."
        ),
        rationale=(
            "A header outside the recognized set -- `Warns:`, `Todo:`, "
            "`Design Notes:` -- hides its body from every rule that grades "
            "section content: RS030, RS041, RS043, and RS047 all read it as "
            "ordinary prose, and tooling walking the Google sections skips "
            "it. The check fires on a margin-level line of up to three "
            "capitalized words closing with a colon, with an indented body "
            "beneath it; a header-shaped line with no indented body reads as "
            "prose and is left alone. Not auto-fixable: where the body "
            "belongs -- folded into prose, or recast under `Raises:` or "
            "`Note:` -- depends on what it says."
        ),
        examples=(
            Example(
                bad=(
                    '"""Verifies the dataset.\n\n'
                    "    Warns:\n"
                    "        RangeWarning: If a decode exceeds the range.\n"
                    '    """'
                ),
                good=(
                    '"""Verifies the dataset.\n\n'
                    "    Warns `RangeWarning` when a decode exceeds the\n"
                    "    range.\n"
                    '    """'
                ),
                note=(
                    "`Warns:` renders under Sphinx's napoleon preset but is "
                    "not in Google's own section set; state the warning in "
                    "body prose (or a `Note:` section) instead."
                ),
            ),
        ),
    ),
    RS_DOCSTRING_SECTION_ALIAS: RuleDoc(
        name="docstring-section-alias",
        summary=(
            "A section header uses the canonical Google spelling: `Args:`, "
            "not `Arguments:`; `Returns:`, not `Return:`; `Yields:`, not "
            "`Yield:`."
        ),
        rationale=(
            "The alias headers parse, so their bodies are still graded, but "
            "one spelling per corpus keeps a section greppable and the "
            "docstrings uniform. `Notes:` and `Examples:` are not aliases: "
            "singular versus plural there is the author's semantic choice. "
            "Auto-fixable: `--fix` rewrites each alias header to its "
            "canonical form in place."
        ),
    ),
    RS_DUPLICATE_DOCSTRING_SECTION: RuleDoc(
        name="duplicate-docstring-section",
        summary=(
            "A docstring holds at most one section per family; a second "
            "`Args:` (or an `Args:` after an `Arguments:`) merges into the "
            "first."
        ),
        rationale=(
            "A duplicated section splits one kind of content across two "
            "places, so a reader stops at the first block and misses the "
            "rest. The duplicate is flagged at its own header; move its "
            "entries into the first block and delete it. Aliases count as "
            "one family, so an `Args:` after an `Arguments:` is a duplicate, "
            "as is a `Notes:` after a `Note:`. Not auto-fixable: merging two "
            "blocks can collide on an entry documented twice, which needs a "
            "human reading."
        ),
    ),
    RS_DOCSTRING_SECTION_ORDER: RuleDoc(
        name="docstring-section-order",
        summary=(
            "Docstring sections follow the canonical Google order: `Args:`, "
            "then `Returns:` or `Yields:`, then `Raises:`, then `Example:`."
        ),
        rationale=(
            "The canonical order reads inputs, then outputs, then failures, "
            "then the example exercising them, so a reader lands on each "
            "section where every other docstring put it. The violation "
            "points at the section sitting below one that should follow it; "
            "the fix is to move the whole section block, body included. "
            "`Note:` and `Attributes:` hold no fixed slot and never fire."
        ),
        examples=(
            Example(
                bad=(
                    "Raises:\n    ValueError: If `x` is bad.\n\n"
                    "Returns:\n    The lease."
                ),
                good=(
                    "Returns:\n    The lease.\n\n"
                    "Raises:\n    ValueError: If `x` is bad."
                ),
            ),
        ),
    ),
    RS_DOUBLE_SPACE_AFTER_PERIOD: RuleDoc(
        name="double-space-after-period",
        summary=(
            "Prose uses a single space after sentence-ending punctuation "
            "(`.`, `!`, `?`), not the old typewriter double space; comments "
            "are checked in Python, TOML, YAML, and shell."
        ),
    ),
}
