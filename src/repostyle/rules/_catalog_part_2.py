"""A partition of the rule explanation catalog."""

from repostyle.rules._catalog_types import Example, RuleDoc
from repostyle.rules._violation import (
    RS_BEHAVIOR_VERIFICATION_ONLY,
    RS_EXCESSIVE_MOCKING,
    RS_FILE_LITERAL_RESTATEMENT,
    RS_REPEATED_TEST_SETUP,
    RS_SHARED_TEST_HELPER,
    RS_TEST_PARAMETRIZATION_CANDIDATE,
)

RULE_DOCS_PART: dict[str, RuleDoc] = {
    RS_EXCESSIVE_MOCKING: RuleDoc(
        name="excessive-mocking",
        summary=(
            "A test builds more than three mocks, a density signal of brittle coupling."
        ),
        rationale=(
            "A test can require many mocks for legitimate reasons, so this rule "
            "marks a review site instead of a defect. Check whether the unit "
            "crosses unnecessary collaborators or whether a fake could expose "
            "caller-visible behavior. Keep the test when each collaborator is "
            "essential. Do not redistribute mock construction merely to cross "
            "the threshold."
        ),
        signals=(
            "Replace a mock of your own collaborator with a port fake under "
            "`tests/fakes/` that records and replays observable interactions.",
            "If the unit needs many mocks to stand up, it may have too many "
            "dependencies -- consider whether it is doing too much.",
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
            "Call-only assertions bind a test to collaborator choreography. They "
            "can pass when a defect preserves the calls and fail when a correct "
            "rewrite changes them. Prefer an observable result or a fake. Delete "
            "the test when no stable behavior is available. Do not add an unrelated "
            "assertion merely to clear the warning."
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
    RS_FILE_LITERAL_RESTATEMENT: RuleDoc(
        name="file-literal-restatement",
        summary="A test asserts only literals it read from a single repo file.",
        rationale=(
            "A test that parses one file, compares what it finds to literals, "
            "and exercises nothing beyond the parser restates that file: the "
            "edit that changes the value changes the assertion beside it, and "
            "no rewrite preserving the behavior a caller relies on can break "
            "it. Such a test costs a second edit site and reads as coverage "
            "without supplying any. Two fixes work. Where the property is "
            "executable -- a container starts, a script runs, a config loads "
            "-- assert it where it executes, since that survives a rewrite of "
            "the file. Where the value has to agree with a second file, read "
            "both and assert they match, which catches the one-sided edit no "
            "single diff shows."
        ),
        signals=(
            "The rule stays silent on a test that reads two or more files, one "
            "comparing a derived value to another derived value, one asserting "
            "across every entry it read, and one whose fixture no module in "
            "scope defines. Fixtures resolve through the requesting class, "
            "the test module, and each `conftest.py` above it; what pytest "
            "supplies from outside that chain is unknowable, so the rule "
            "declines to guess. A `@pytest.mark.parametrize` argument reads "
            "as one of those undefined fixtures, so a parametrized test goes "
            "unexamined.",
            "A deliberate single-file pin -- a value with no second home and "
            "no executable surface -- takes `# style: ignore[RS060]` with the "
            "reason it cannot be checked anywhere better.",
        ),
        examples=(
            Example(
                bad=(
                    "compose = yaml.safe_load(_COMPOSE_PATH.read_text())\n"
                    'assert compose["services"]["drain"]["user"] == "1000:1000"'
                ),
                good=(
                    "compose = yaml.safe_load(_COMPOSE_PATH.read_text())\n"
                    "declared = _DOCKERFILE_PATH.read_text()\n"
                    'assert compose["services"]["drain"]["user"].split(":")[0] '
                    "in declared"
                ),
                note=(
                    "The uid has to match the one the image declares, so read "
                    "both files rather than quoting the number twice."
                ),
            ),
        ),
    ),
    RS_SHARED_TEST_HELPER: RuleDoc(
        name="shared-test-helper",
        summary=(
            "Matching substantial helpers or compatible fixtures across test "
            "files are candidates for one shared definition."
        ),
        rationale=(
            "The rule compares conservative syntax, local binding relationships, "
            "and external dependency identities. A match is evidence of repeated "
            "test support code, not proof that the definitions share semantics or "
            "lifecycle. Place a shared helper in the narrowest support module its "
            "callers already own. Use a fixture when pytest should supply a value; "
            "use a builder or ordinary helper when each test should choose when and "
            "how to construct it."
        ),
        signals=(
            "Check mutable state, cleanup, fixture scope, and isolation before "
            "consolidating. Keep separate definitions when their contracts only "
            "happen to have the same current syntax.",
            "A line, block, or file suppression silences that occurrence. It can "
            "remain structural evidence for an unsuppressed peer; an `exclude` "
            "glob removes the file from both evidence and reporting.",
            "Dynamic namespace access, comprehensions, nested scopes, and other "
            "uncertain bindings are skipped rather than guessed. Unresolved names "
            "under wildcard imports stay file-specific and cannot create a "
            "cross-file match.",
        ),
    ),
    RS_TEST_PARAMETRIZATION_CANDIDATE: RuleDoc(
        name="test-parametrization-candidate",
        summary=(
            "Three tests with one named contract, the same supported structure, "
            "and differing scalar body literals are candidates for "
            "parametrization."
        ),
        rationale=(
            "Parametrization can state repeated behavior as one contract plus a "
            "table of cases. The rule preserves signatures, marks, decorators, "
            "call targets, operations, and literal types, requires at least two "
            "meaningful test-name words in common, and requires at least one "
            "literal position to vary. It keeps multi-line fixture programs "
            "distinct. It does not justify adding conditionals or combining cases "
            "with different behavior."
        ),
        examples=(
            Example(
                bad=(
                    "def test_Parse_AcceptsAlpha():\n    assert parse('a') == 1\n\n"
                    "def test_Parse_AcceptsBeta():\n    assert parse('b') == 2\n\n"
                    "def test_Parse_AcceptsGamma():\n    assert parse('c') == 3"
                ),
                good=(
                    "@pytest.mark.parametrize(\n"
                    "    ('text', 'expected'), [('a', 1), ('b', 2), ('c', 3)]\n"
                    ")\n"
                    "def test_Parse_AcceptsNamedCase(text, expected):\n"
                    "    assert parse(text) == expected"
                ),
                note=(
                    "Give rows readable ids or names when the original test names "
                    "carried behavior a failure report should retain."
                ),
            ),
        ),
    ),
    RS_REPEATED_TEST_SETUP: RuleDoc(
        name="repeated-test-setup",
        summary=(
            "Three tests sharing a leading assignment sequence that includes a "
            "call are candidates for a builder or fixture."
        ),
        rationale=(
            "Repeated construction can obscure the behavior each test varies. The "
            "rule compares exact leading assignments, including values, call "
            "targets, and dependencies, then reports the longest shared prefix for "
            "each matching group. The repeated call may still be the action under "
            "test, so the warning does not label it setup."
        ),
        signals=(
            "Prefer a builder or ordinary helper when tests need fresh values or "
            "different construction timing. Choose a fixture only after checking "
            "scope, teardown, mutation, and isolation.",
            "This rule is independent of the parametrization rule. Both may report "
            "the same tests because consolidating setup and tabulating cases are "
            "separate review choices.",
        ),
    ),
}
