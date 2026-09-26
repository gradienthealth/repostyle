"""A partition of the rule explanation catalog."""

from repostyle.rules._catalog_types import Example, RuleDoc
from repostyle.rules._violation import (
    RS_ARG_DESCRIBED_IN_PROSE,
    RS_BOOLEAN_PREFIX_REQUIRED,
    RS_EXCEPTION_ALIAS,
    RS_FILENAME_CONVENTION,
    RS_IMPERATIVE_DOCSTRING_OPENING,
    RS_NO_MAKE_IN_PRODUCTION,
    RS_RETURN_DESCRIBED_IN_PROSE,
    RS_SHOULD_BE_PRIVATE,
    RS_TERMINAL_PUNCTUATION,
    RS_TOO_MANY_POSITIONAL_ARGS,
)
from repostyle.rules.imperative_verbs import NON_TRIVIAL_CONJUGATIONS

RULE_DOCS_PART: dict[str, RuleDoc] = {
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
            "(`.`, `!`, or `?`); comments are checked in Python, TOML, YAML, and shell."
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
        rationale=(
            "A reader and a documentation tool both look for the return "
            "contract under a `Returns:` or `Yields:` caption, so a body "
            "paragraph that carries it instead hides it. The rule reads the "
            "phrasing, not the verb, so recasting the sentence does not "
            "satisfy it -- move the description into a section. The summary "
            "line is exempt: it states the contract rather than narrating it, "
            "and a one-line summary is often all a scalar return needs."
        ),
        signals=(
            "A body sentence led by a return verb (`Returns the lease.`, "
            "`Yields each row.`): move it under `Returns:` or `Yields:`.",
            "A body sentence whose subject is the returned thing (`The result "
            "is ...`, `The return value is ...`): same move.",
            "A return verb mid-sentence under an input or condition subject "
            "(`A malformed file returns None.`): same move.",
        ),
        examples=(
            Example(
                bad="A file of any other type yields nothing.",
                good="Returns:\n    Each comment, and nothing for another type.",
                note=(
                    "The phrasing does not matter; the section it belongs under does."
                ),
            ),
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
            "configurable -- `[tool.repostyle.filename-extensions]` replaces "
            "the extension map wholesale, `filename-case` takes `snake` or "
            "`none`. A curated set of tool- or ecosystem-mandated fixed "
            "names (`README.md`, `CHANGELOG.md`, `LICENSE`, `CODEOWNERS`, "
            "`CLAUDE.md`, ...) is exempt from both checks by default, so a "
            "repo never re-lists them; `filename-ignore` extends that set "
            "with any further fixed-name file a tool mandates rather than "
            "renaming it. An "
            "extensionless name like `Dockerfile` or `LICENSE` only reaches "
            "this rule if the consuming repo's own pre-commit hook is "
            "configured to pass it -- the shipped hook and a bare directory "
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
}
