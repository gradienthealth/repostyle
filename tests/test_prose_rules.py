import sys
from pathlib import Path

import pytest

from repostyle.rules import (
    RS_BULLET_ITEM_CASING,
    RS_INLINE_NUMBERED_LIST,
    RS_NONSTANDARD_DASH,
    RS_TERMINAL_PUNCTUATION,
    check_bullet_item_casing,
    check_bullet_item_casing_in_comments,
    check_comment_terminal_punctuation,
    check_inline_numbered_list,
    check_nonstandard_dash_in_comments,
    check_nonstandard_dash_in_docstrings,
)

_DOC_PATH = Path("src/x.py")

# PEP 695 type-alias / type-parameter syntax only parses on Python 3.12+, so
# these cases skip on 3.11, where the source is a SyntaxError the checker
# correctly cannot inspect (such code cannot exist on 3.11 anyway).
_REQUIRES_PEP695 = pytest.mark.skipif(
    sys.version_info < (3, 12), reason="PEP 695 syntax requires Python 3.12+"
)

_ATTRIBUTES_BLOCK_HEADER = (
    "class Demographics:\n"
    '    """Patient demographics.\n'
    "\n"
    "    Attributes:\n"
    "        name: full name.\n"
    '    """\n'
)
_ATTRIBUTES_NO_BLOCK = 'class Demographics:\n    """Patient demographics."""\n'
_ATTRIBUTES_INLINE_PROSE = (
    "class Demographics:\n"
    '    """Mentions Attributes: inline but not as section header."""\n'
)


class TestCheckCommentTerminalPunctuation:
    @pytest.mark.parametrize(
        "source",
        [
            "# Does a foo\nx = 1\n",
            "x = 1  # Does a foo\n",
            "# This comment wraps across two lines and ends\n# with a period.\nx = 1\n",
            "x = 1  # noqa: E501\n",
            "# def helper():\n#     return 1\nx = 1\n",
            "# The spec lives at\n# https://example.com/spec\nx = 1\n",
            "# -*- coding: utf-8 -*-\nx = 1\n",
            "# handles the retry path.\nx = 1\n",
            "# First standalone note\n\n# Second standalone note\nx = 1\n",
            "# Rescue still fires without the apostrophe\n"
            "# codespell:ignore-begin\nx = 1\n",
            "# Spawns the subprocess with a fixed argv\n# nosec\nx = 1\n",
        ],
        ids=[
            "standalone-fragment",
            "trailing-fragment",
            "multiline-prose-with-period",
            "trailing-directive",
            "commented-out-code",
            "url-tail",
            "coding-declaration",
            "lowercase-not-prose",
            "blank-gap-separate-blocks",
            "codespell-directive-splits-block",
            "nosec-directive-splits-block",
        ],
    )
    def test_ConformingComment_NoViolation(self, source: str) -> None:
        assert list(check_comment_terminal_punctuation(_DOC_PATH, source)) == []

    def test_StandaloneFragmentWithPeriod_FlagsFragment(self) -> None:
        violations = list(
            check_comment_terminal_punctuation(_DOC_PATH, "# Does a foo.\nx = 1\n")
        )
        assert [(v.rule, v.line) for v in violations] == [(RS_TERMINAL_PUNCTUATION, 1)]
        assert "fragment" in violations[0].message

    def test_TrailingProseWithPeriod_FlagsFragmentAtColumn(self) -> None:
        source = "x = 1  # Returns the widget.\n"
        violations = list(check_comment_terminal_punctuation(_DOC_PATH, source))
        assert (violations[0].line, violations[0].col) == (1, 8)

    def test_MultilineProseWithoutTerminal_FlagsProseAtLastLine(self) -> None:
        source = (
            "# This comment wraps across two lines and ends\n"
            "# without any terminal mark\nx = 1\n"
        )
        violations = list(check_comment_terminal_punctuation(_DOC_PATH, source))
        assert [(v.rule, v.line) for v in violations] == [(RS_TERMINAL_PUNCTUATION, 2)]
        assert "prose" in violations[0].message

    def test_MultiSentenceSingleLineWithoutTerminal_FlagsProse(self) -> None:
        source = "# I like pie. I like cake\nx = 1\n"
        violations = list(check_comment_terminal_punctuation(_DOC_PATH, source))
        assert [(v.rule, v.line) for v in violations] == [(RS_TERMINAL_PUNCTUATION, 1)]

    @pytest.mark.parametrize(
        "path",
        [Path("config.toml"), Path("config.yaml")],
        ids=["toml", "yaml"],
    )
    def test_MultilineProseWithoutTerminal_FlagsAcrossCommentLanguages(
        self, path: Path
    ) -> None:
        source = (
            "# This comment spans two lines and ends\n"
            "# without any terminal mark\nkey: 1\n"
        )
        violations = list(check_comment_terminal_punctuation(path, source))
        assert [(v.rule, v.line) for v in violations] == [(RS_TERMINAL_PUNCTUATION, 2)]

    def test_YamlTrailingMultiSentence_FlagsProse(self) -> None:
        source = "key: 1  # First sentence. Second sentence with no terminal mark\n"
        violations = list(
            check_comment_terminal_punctuation(Path("config.yaml"), source)
        )
        assert [(v.rule, v.line) for v in violations] == [(RS_TERMINAL_PUNCTUATION, 1)]

    def test_NonPythonFile_NoViolation(self) -> None:
        source = "# A prose comment with a trailing period.\n"
        assert list(check_comment_terminal_punctuation(Path("notes.txt"), source)) == []

    def test_DirectiveSplitsBlockFromProse_NoViolation(self) -> None:
        source = "# A standalone prose comment line\n# type: ignore\nx = 1\n"
        assert list(check_comment_terminal_punctuation(_DOC_PATH, source)) == []

    def test_HashInsideYamlQuotedScalar_NotTreatedAsComment(self) -> None:
        source = 'key: "a value. with a period inside"\n'
        assert (
            list(check_comment_terminal_punctuation(Path("config.yaml"), source)) == []
        )


class TestCheckBulletItemCasing:
    @pytest.mark.parametrize(
        "source",
        [
            'def f():\n    """Do it.\n\n    - the thing\n'
            '    - the other thing\n    """\n',
            'def f():\n    """Do it.\n\n    - The thing. Does a foo.\n'
            '    - The other thing.\n    """\n',
            'def f():\n    """Do it.\n\n    - `json` output. Goes here.\n'
            '    - The other thing.\n    """\n',
            'def f():\n    """Do it.\n\n    - json.dumps output. Goes here.\n'
            '    - The other thing.\n    """\n',
            'def f():\n    """Do it.\n\n    - skip_lines is honored. Always.\n'
            '    - The other thing.\n    """\n',
            'def f():\n    """Do it.\n\n    - 3 retries at most. Then stop.\n'
            '    - The other thing.\n    """\n',
            'def f():\n    """Do it.\n\n    ```\n    - the fence. Not prose.\n'
            '    ```\n    """\n',
            'def f():\n    """Do it.\n\n    - uses `foo. Bar` internally\n'
            '    - the other thing\n    """\n',
        ],
        ids=[
            "all-fragments-lowercase",
            "multi-sentence-all-capitalized",
            "opens-backtick-span",
            "opens-dotted-path",
            "opens-distinctive-token",
            "opens-digit",
            "bullets-inside-fence",
            "boundary-inside-backticks",
        ],
    )
    def test_ConformingList_NoViolation(self, source: str) -> None:
        assert list(check_bullet_item_casing(_DOC_PATH, source)) == []

    def test_LowercaseMultiSentenceItem_FlagsAtMarker(self) -> None:
        source = (
            'def f():\n    """Do it.\n\n'
            "    - the thing. Does a foo.\n"
            '    - The other thing.\n    """\n'
        )
        violations = list(check_bullet_item_casing(_DOC_PATH, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_BULLET_ITEM_CASING
        assert (violations[0].line, violations[0].col) == (4, 5)
        assert "capital" in violations[0].message

    def test_LowercaseSiblingOfMultiSentenceItem_Flags(self) -> None:
        source = (
            'def f():\n    """Do it.\n\n'
            "    - The thing. Does a foo.\n"
            '    - the other thing\n    """\n'
        )
        violations = list(check_bullet_item_casing(_DOC_PATH, source))
        assert [(v.rule, v.line) for v in violations] == [(RS_BULLET_ITEM_CASING, 5)]

    def test_WrappedItemSecondSentenceOnContinuation_Flags(self) -> None:
        source = (
            'def f():\n    """Do it.\n\n'
            "    - the thing that wraps onto a\n"
            '      second line. Also does a foo.\n    """\n'
        )
        violations = list(check_bullet_item_casing(_DOC_PATH, source))
        assert [(v.rule, v.line) for v in violations] == [(RS_BULLET_ITEM_CASING, 4)]

    def test_ListsSplitByParagraph_JudgedIndependently(self) -> None:
        source = (
            'def f():\n    """Do it.\n\n'
            "    - The thing. Does a foo.\n\n"
            "    A separating paragraph.\n\n"
            '    - the other thing\n    """\n'
        )
        assert list(check_bullet_item_casing(_DOC_PATH, source)) == []

    def test_NestedDeeperItem_JudgedAsOwnList(self) -> None:
        source = (
            'def f():\n    """Do it.\n\n'
            "    - The thing. Does a foo.\n"
            "      - nested fragment\n"
            '    - The other thing.\n    """\n'
        )
        assert list(check_bullet_item_casing(_DOC_PATH, source)) == []


class TestCheckBulletItemCasingInComments:
    def test_AllFragmentList_NoViolation(self) -> None:
        source = "# The plan:\n# - the thing\n# - the other thing\nx = 1\n"
        assert list(check_bullet_item_casing_in_comments(_DOC_PATH, source)) == []

    def test_LowercaseMultiSentenceItem_FlagsAtBulletLine(self) -> None:
        source = "# - the thing. Does a foo.\n# - The other thing.\nx = 1\n"
        violations = list(check_bullet_item_casing_in_comments(_DOC_PATH, source))
        assert [(v.rule, v.line, v.col) for v in violations] == [
            (RS_BULLET_ITEM_CASING, 1, 1)
        ]

    def test_WrappedCommentItem_JoinsContinuation(self) -> None:
        source = (
            "# - the thing that wraps onto\n"
            "#   a second line. Also does a foo.\n"
            "# - The other thing.\nx = 1\n"
        )
        violations = list(check_bullet_item_casing_in_comments(_DOC_PATH, source))
        assert [(v.rule, v.line) for v in violations] == [(RS_BULLET_ITEM_CASING, 1)]

    def test_ProseLineBetweenBullets_SplitsTheList(self) -> None:
        source = (
            "# - The thing. Does a foo.\n"
            "# An interrupting sentence at the margin.\n"
            "# - the other thing\nx = 1\n"
        )
        assert list(check_bullet_item_casing_in_comments(_DOC_PATH, source)) == []


class TestCheckInlineNumberedList:
    @pytest.mark.parametrize(
        "source",
        [
            'def f():\n    """Runs the workflow: 1. Loads the file. 2. Validates it."""\n',
            'def f():\n    """Runs the workflow: 1. Loads the file.\n'
            '    2. Validates it.\n    """\n',
            'def f():\n    """Runs the workflow: 3) Loads the file. 4) Validates it."""\n',
        ],
        ids=["one-line", "wrapped-source", "parenthesized-markers"],
    )
    def test_InlineSequence_FlagsViolation(self, source: str) -> None:
        violations = list(check_inline_numbered_list(_DOC_PATH, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_INLINE_NUMBERED_LIST
        assert "own line" in violations[0].message

    def test_InlineSequence_ReportsFirstMarker(self) -> None:
        source = 'def f():\n    """Runs: 1. Loads. 2. Validates."""\n'
        violations = list(check_inline_numbered_list(_DOC_PATH, source))
        assert (violations[0].line, violations[0].col) == (2, 14)

    @pytest.mark.parametrize(
        "source",
        [
            'def f():\n    """Runs the workflow.\n\n'
            "    1. Loads the file and keeps enough text here to establish the\n"
            "       aligned continuation.\n"
            '    2. Validates it.\n    """\n',
            'def f():\n    """Runs the workflow.\n\n'
            "    1. Loads the file.\n"
            "    2. Validates it:\n\n"
            '       ```\n       validate input\n       ```\n    """\n',
            'def f():\n    """Supports version 1. Version 3. remains readable."""\n',
            'def f():\n    """Describes version 1. here.\n\n'
            '    Describes version 2. there.\n    """\n',
            'def f():\n    """Names `1. inline 2. markers` as sample text."""\n',
            'def f():\n    """Shows a sample.\n\n'
            "    Example:\n"
            "        workflow: 1. load 2. validate\n"
            '    """\n',
        ],
        ids=[
            "newline-list-with-continuation",
            "newline-list-with-fence",
            "nonconsecutive-numbers",
            "separate-paragraphs",
            "code-span",
            "example-section",
        ],
    )
    def test_ConformingOrNonProseSequence_NoViolation(self, source: str) -> None:
        assert list(check_inline_numbered_list(_DOC_PATH, source)) == []

    def test_UnparseableSource_NoViolation(self) -> None:
        source = 'def (:\n    """Steps: 1. Load. 2. Validate."""\n'
        assert list(check_inline_numbered_list(_DOC_PATH, source)) == []


class TestCheckNonstandardDashInDocstrings:
    @pytest.mark.parametrize(
        "source",
        [
            'def f():\n    """Returns the lease -- or `None` when expired."""\n',
            'def f():\n    """Retries 3 - 5 times at most."""\n',
            'def f():\n    """Computes `n - 1` for the index."""\n',
            'def f():\n    """Pass --fix to rewrite in place."""\n',
            'def f():\n    """See https://x.test/a--b for details."""\n',
            'def f():\n    """Covers RS013–RS016 in one pass."""\n',  # noqa: RUF001
            'def f():\n    """Do it.\n\n    Example:\n        run — now\n    """\n',
        ],
        ids=[
            "standard-dash",
            "numeric-range",
            "backticked-arithmetic",
            "cli-flag",
            "url",
            "unspaced-en-dash-range",
            "em-dash-in-example-section",
        ],
    )
    def test_ConformingProse_NoViolation(self, source: str) -> None:
        assert list(check_nonstandard_dash_in_docstrings(_DOC_PATH, source)) == []

    @pytest.mark.parametrize(
        ("prose", "found"),
        [
            ("the lease — or nothing", " — "),
            ("the lease—or nothing", "—"),
            ("the lease – or nothing", " – "),  # noqa: RUF001
            ("the lease - or nothing", " - "),
            ("the lease--or nothing", "--"),
        ],
        ids=[
            "spaced-em-dash",
            "glued-em-dash",
            "spaced-en-dash",
            "spaced-hyphen",
            "glued-double-hyphen",
        ],
    )
    def test_NonstandardDash_FlagsWithFormInMessage(
        self, prose: str, found: str
    ) -> None:
        source = f'def f():\n    """Returns {prose}."""\n'
        violations = list(check_nonstandard_dash_in_docstrings(_DOC_PATH, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_NONSTANDARD_DASH
        assert repr(found) in violations[0].message

    def test_EntryDescriptionDash_FlagsAtOffset(self) -> None:
        source = (
            'def f(bar):\n    """Do it.\n\n    Args:\n'
            '        bar: A bar — the good kind.\n    """\n'
        )
        violations = list(check_nonstandard_dash_in_docstrings(_DOC_PATH, source))
        assert [(v.rule, v.line, v.col) for v in violations] == [
            (RS_NONSTANDARD_DASH, 5, 19)
        ]


class TestCheckNonstandardDashInComments:
    def test_StandardDash_NoViolation(self) -> None:
        source = "# resolves the config -- falling back\nx = 1\n"
        assert list(check_nonstandard_dash_in_comments(_DOC_PATH, source)) == []

    def test_TrailingCommentDash_Flags(self) -> None:
        source = "x = 1  # a fallback – slower but safe\n"  # noqa: RUF001
        violations = list(check_nonstandard_dash_in_comments(_DOC_PATH, source))
        assert [(v.rule, v.line) for v in violations] == [(RS_NONSTANDARD_DASH, 1)]

    def test_CommentedOutCode_NotFlagged(self) -> None:
        source = "# width - margin\nx = 1\n"
        assert list(check_nonstandard_dash_in_comments(_DOC_PATH, source)) == []

    def test_TwoFaultsOnOneLine_FlagsBoth(self) -> None:
        source = "# a fallback — slower — but safe\nx = 1\n"
        violations = list(check_nonstandard_dash_in_comments(_DOC_PATH, source))
        assert [v.rule for v in violations] == [RS_NONSTANDARD_DASH] * 2
