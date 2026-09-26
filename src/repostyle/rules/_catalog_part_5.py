"""A partition of the rule explanation catalog."""

from repostyle.rules._catalog_types import Example, RuleDoc
from repostyle.rules._violation import (
    RS_DEEPLY_NESTED_TYPE,
    RS_DOC_SUMMARY_OVERFLOW,
    RS_GLUED_CODE_SPAN,
    RS_RAISE_DESCRIBED_IN_PROSE,
    RS_UNBACKTICKED_CODE_REFERENCE,
    RS_UNBACKTICKED_SIBLING_SYMBOL,
)

RULE_DOCS_PART: dict[str, RuleDoc] = {
    RS_DOC_SUMMARY_OVERFLOW: RuleDoc(
        name="doc-summary-overflow",
        summary="A docstring summary line fills within 79 columns.",
        rationale=(
            "PEP 257 and Google style require a docstring summary to be "
            "exactly one physical line, so unlike a body paragraph it has no "
            "second line to spread overflow onto -- `doc-fill`'s `--fix` "
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
            "A docstring wraps a code name it references -- a parameter, an "
            "import, a class, `None`/`True`/`False` -- in single backticks."
        ),
        rationale=(
            "The house style sets a code token in single backticks so prose "
            "reads apart from the identifiers it names. A linter cannot decide "
            "this for an arbitrary word, so the check stays mechanical by "
            "firing only where two signals agree: the word matches a name the "
            "module itself binds (a parameter, import, function, class, or "
            "accessed attribute) or a literal constant, and its shape rules "
            "out plain English -- an underscore, a digit, or an interior "
            "capital beside a lowercase letter (`skip_lines`, `HttpClient`). A "
            "literal (`None`/`True`/`False`) fires mid-sentence but not at a "
            "sentence start, where its capital could open an English clause. A "
            "plain-lowercase name (a `path` parameter) and a Titlecase or "
            "all-caps word that also reads as English (`Path`, `WARNING`) are "
            "left to review, since no rule can tell the reference from the "
            "word. Grounding the match in the module's own names is what lets "
            "a code-shaped word the module never binds -- a proper noun, or a "
            "name shown only in an example -- pass untouched: the shape marks a "
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
            "onto its closing backtick -- a possessive, a plural, or a verb "
            "ending -- reads as part of the identifier and breaks the span in "
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
            "token qualifies only when its shape rules out plain English -- an "
            "underscore, a digit, or an interior capital beside a lowercase "
            "letter -- and when the same file carries it verbatim inside a "
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
            "beyond that counts the same -- a `tuple` or a `Callable` is no "
            "easier to read nested -- so the remedy is to give the inner "
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
            "unstructured docstring prose."
        ),
    ),
}
