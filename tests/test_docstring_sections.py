import sys
from pathlib import Path

import pytest

from repostyle.rules import (
    RS_DOCSTRING_SECTION_ALIAS,
    RS_DOCSTRING_SECTION_ORDER,
    RS_DUPLICATE_DOCSTRING_SECTION,
    RS_INVALID_DOCSTRING_SECTION,
    RS_LOWERCASE_ENTRY_DESCRIPTION,
    RS_NO_ATTRIBUTES_BLOCK,
    RS_TERMINAL_PUNCTUATION,
    check_docstring_section_alias,
    check_docstring_section_order,
    check_docstring_terminal_punctuation,
    check_duplicate_docstring_section,
    check_invalid_docstring_section,
    check_lowercase_entry_description,
    check_no_attributes_block,
)

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
_DOC_PATH = Path("src/x.py")


class TestCheckNoAttributesBlock:
    def test_AttributesBlockHeader_FlagsViolation(self) -> None:
        violations = list(
            check_no_attributes_block(_DOC_PATH, _ATTRIBUTES_BLOCK_HEADER)
        )
        assert len(violations) == 1
        assert violations[0].rule == RS_NO_ATTRIBUTES_BLOCK

    def test_ModuleDocstring_ColumnFallsBackToOne(self) -> None:
        source = '"""Attributes:\n    name: full name.\n"""\n'
        violations = list(check_no_attributes_block(_DOC_PATH, source))
        assert (violations[0].line, violations[0].col) == (1, 1)

    @pytest.mark.parametrize(
        "source",
        [_ATTRIBUTES_NO_BLOCK, _ATTRIBUTES_INLINE_PROSE],
        ids=["no-block", "inline-prose"],
    )
    def test_NoBlockHeader_NoViolation(self, source: str) -> None:
        assert list(check_no_attributes_block(_DOC_PATH, source)) == []


_DOC_SINGLE_LINE_ENTRY = (
    'def f(foo):\n    """Do the thing.\n\n    Args:\n'
    '        foo: the widget to process.\n    """\n'
)
_DOC_MULTI_LINE_ENTRY = (
    'def f(bar):\n    """Do the thing.\n\n    Args:\n'
    "        bar: the widget that wraps across\n"
    '            two lines of description.\n    """\n'
)
_DOC_COLON_INTRO = (
    'def f():\n    """Do the thing.\n\n    The steps are as follows:\n    """\n'
)
_DOC_EXAMPLE_SECTION = (
    'def f():\n    """Do the thing.\n\n    Example:\n'
    '        >>> f()\n        result\n    """\n'
)
# A Returns description that wraps at the entry margin (no hanging indent) is
# one multi-line entry, not two single-line labels.
_DOC_SAME_INDENT_RETURNS = (
    'def f():\n    """Do the thing.\n\n    Returns:\n'
    "        A tuple of the parsed bundle and the\n"
    '        count of records.\n    """\n'
)


class TestCheckDocstringTerminalPunctuation:
    @pytest.mark.parametrize(
        "source",
        [
            'def f():\n    """Resolve the lease."""\n',
            'def f():\n    """Ready to go?"""\n',
            'def f():\n    """Do it.\n\n    The body states the contract.\n    """\n',
            _DOC_SINGLE_LINE_ENTRY,
            _DOC_MULTI_LINE_ENTRY,
            _DOC_COLON_INTRO,
            _DOC_EXAMPLE_SECTION,
            _DOC_SAME_INDENT_RETURNS,
            'def f():\n    """Do it.\n\n    See the spec at\n'
            '    https://example.com/spec\n    """\n',
            'def f():\n    """Do it.\n\n    - first point\n    - second\n    """\n',
            'def f():\n    """Do it.\n\n    ```\n    code here\n    ```\n    """\n',
        ],
        ids=[
            "summary-with-period",
            "summary-question-mark",
            "body-with-period",
            "single-line-entry-with-period",
            "multi-line-entry-with-period",
            "colon-list-intro",
            "example-section-code",
            "same-indent-returns-with-period",
            "body-url-tail",
            "bullet-list",
            "fenced-code",
        ],
    )
    def test_ConformingDocstring_NoViolation(self, source: str) -> None:
        assert list(check_docstring_terminal_punctuation(_DOC_PATH, source)) == []

    def test_SingleLineSummaryWithoutTerminal_FlagsAtSummary(self) -> None:
        source = 'def f():\n    """Resolve the lease"""\n'
        violations = list(check_docstring_terminal_punctuation(_DOC_PATH, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_TERMINAL_PUNCTUATION
        assert (violations[0].line, violations[0].col) == (2, 5)
        assert "terminal punctuation" in violations[0].message

    def test_ModuleDocstringWithoutTerminal_FlagsAtColumnOne(self) -> None:
        violations = list(
            check_docstring_terminal_punctuation(_DOC_PATH, '"""Resolve the lease"""\n')
        )
        assert [(v.rule, v.line, v.col) for v in violations] == [
            (RS_TERMINAL_PUNCTUATION, 1, 1)
        ]

    def test_BodyParagraphWithoutTerminal_FlagsAtBody(self) -> None:
        source = (
            'def f():\n    """Do it.\n\n    The body has no terminal mark\n    """\n'
        )
        violations = list(check_docstring_terminal_punctuation(_DOC_PATH, source))
        assert [(v.rule, v.line) for v in violations] == [(RS_TERMINAL_PUNCTUATION, 4)]

    def test_MultiLineSummaryWithoutTerminal_FlagsAtLastLine(self) -> None:
        source = (
            'def f():\n    """Resolve the lease for the tenant named in the\n'
            '    request payload\n    """\n'
        )
        violations = list(check_docstring_terminal_punctuation(_DOC_PATH, source))
        assert [(v.rule, v.line) for v in violations] == [(RS_TERMINAL_PUNCTUATION, 3)]

    def test_SingleLineEntryWithoutTerminal_FlagsAtEntry(self) -> None:
        source = (
            'def f(foo):\n    """Do the thing.\n\n    Args:\n'
            '        foo: the widget\n    """\n'
        )
        violations = list(check_docstring_terminal_punctuation(_DOC_PATH, source))
        assert [(v.rule, v.line) for v in violations] == [(RS_TERMINAL_PUNCTUATION, 5)]

    def test_RaisesEntryWithoutTerminal_FlagsAtEntry(self) -> None:
        source = (
            'def f():\n    """Do the thing.\n\n    Raises:\n'
            '        ValueError: when the input is bad\n    """\n'
        )
        violations = list(check_docstring_terminal_punctuation(_DOC_PATH, source))
        assert [(v.rule, v.line) for v in violations] == [(RS_TERMINAL_PUNCTUATION, 5)]

    def test_FlushLineAfterEntryBullet_StillGraded(self) -> None:
        source = (
            'def f(foo):\n    """Do it.\n\n    Args:\n'
            "        foo: Something listed:\n"
            "            - a bullet item\n"
            "        a flush follow-on line with no mark\n"
            '    """\n'
        )
        violations = list(check_docstring_terminal_punctuation(_DOC_PATH, source))
        assert [(v.rule, v.line) for v in violations] == [(RS_TERMINAL_PUNCTUATION, 7)]

    def test_WrappedBulletContinuation_NotFlagged(self) -> None:
        source = (
            'def f():\n    """Do it.\n\n'
            "    - a wrapped bullet item whose continuation\n"
            "      line carries no terminal mark\n"
            '    """\n'
        )
        assert list(check_docstring_terminal_punctuation(_DOC_PATH, source)) == []

    def test_MultiLineEntryWithoutTerminal_FlagsAtLastLine(self) -> None:
        source = (
            'def f():\n    """Do the thing.\n\n    Returns:\n'
            "        A tuple of the parsed bundle and the\n"
            '        count of records\n    """\n'
        )
        violations = list(check_docstring_terminal_punctuation(_DOC_PATH, source))
        assert [(v.rule, v.line) for v in violations] == [(RS_TERMINAL_PUNCTUATION, 6)]

    def test_MultiEntrySection_FlagsOnlyOffendingEntry(self) -> None:
        source = (
            'def f(foo, bar):\n    """Do the thing.\n\n    Args:\n'
            "        foo: the first widget.\n"
            '        bar: the second widget\n    """\n'
        )
        violations = list(check_docstring_terminal_punctuation(_DOC_PATH, source))
        assert [(v.rule, v.line) for v in violations] == [(RS_TERMINAL_PUNCTUATION, 6)]


class TestCheckLowercaseEntryDescription:
    @pytest.mark.parametrize(
        "source",
        [
            'def f(foo):\n    """Do the thing.\n\n    Args:\n'
            '        foo: A widget.\n    """\n',
            'def f():\n    """Do the thing.\n\n    Returns:\n'
            '        The parsed bundle.\n    """\n',
            'def f():\n    """Do the thing.\n\n    Raises:\n'
            '        ValueError: If the input is bad.\n    """\n',
            'def f(foo):\n    """Do the thing.\n\n    Args:\n'
            '        foo: `None` when unset.\n    """\n',
            'def f(foo):\n    """Do the thing.\n\n    Args:\n'
            '        foo: json.dumps of the payload.\n    """\n',
            'def f(foo):\n    """Do the thing.\n\n    Args:\n'
            '        foo: col_offset of the node.\n    """\n',
            'def f(foo):\n    """Do the thing.\n\n    Args:\n'
            '        foo: 3 retries at most.\n    """\n',
            'def f(foo):\n    """Do the thing.\n\n    Args:\n        foo:\n    """\n',
        ],
        ids=[
            "args-capitalized",
            "returns-nameless-capitalized",
            "raises-capitalized",
            "opens-backtick-span",
            "opens-dotted-path",
            "opens-distinctive-token",
            "opens-digit",
            "empty-description",
        ],
    )
    def test_ConformingEntry_NoViolation(self, source: str) -> None:
        assert list(check_lowercase_entry_description(_DOC_PATH, source)) == []

    def test_LowercaseArgsDescription_FlagsAtEntry(self) -> None:
        source = (
            'def f(bar):\n    """Do the thing.\n\n    Args:\n'
            '        bar: a bar.\n    """\n'
        )
        violations = list(check_lowercase_entry_description(_DOC_PATH, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_LOWERCASE_ENTRY_DESCRIPTION
        assert (violations[0].line, violations[0].col) == (5, 9)
        assert "lowercase" in violations[0].message

    def test_LowercaseRaisesDescription_FlagsAtEntry(self) -> None:
        source = (
            'def f():\n    """Do the thing.\n\n    Raises:\n'
            '        NotFoundError: if a foo is not found.\n    """\n'
        )
        violations = list(check_lowercase_entry_description(_DOC_PATH, source))
        assert [(v.rule, v.line) for v in violations] == [
            (RS_LOWERCASE_ENTRY_DESCRIPTION, 5)
        ]

    def test_NamelessReturnsLowercase_FlagsAtEntry(self) -> None:
        source = (
            'def f():\n    """Do the thing.\n\n    Returns:\n'
            '        the parsed bundle.\n    """\n'
        )
        violations = list(check_lowercase_entry_description(_DOC_PATH, source))
        assert [(v.rule, v.line) for v in violations] == [
            (RS_LOWERCASE_ENTRY_DESCRIPTION, 5)
        ]

    def test_MultiLineEntryLowercase_FlagsAtFirstLine(self) -> None:
        source = (
            'def f():\n    """Do the thing.\n\n    Returns:\n'
            "        the parsed bundle and the\n"
            '        record count.\n    """\n'
        )
        violations = list(check_lowercase_entry_description(_DOC_PATH, source))
        assert [(v.rule, v.line) for v in violations] == [
            (RS_LOWERCASE_ENTRY_DESCRIPTION, 5)
        ]

    def test_MultiEntrySection_FlagsOnlyOffendingEntry(self) -> None:
        source = (
            'def f(foo, bar):\n    """Do the thing.\n\n    Args:\n'
            "        foo: A first widget.\n"
            '        bar: a second widget.\n    """\n'
        )
        violations = list(check_lowercase_entry_description(_DOC_PATH, source))
        assert [(v.rule, v.line) for v in violations] == [
            (RS_LOWERCASE_ENTRY_DESCRIPTION, 6)
        ]


class TestCheckInvalidDocstringSection:
    @pytest.mark.parametrize(
        "source",
        [
            'def f(x):\n    """Do the thing.\n\n    Args:\n'
            "        x: An x.\n\n    Returns:\n        The thing.\n\n"
            "    Raises:\n        ValueError: If x is bad.\n\n    Note:\n"
            '        A note.\n\n    Example:\n        >>> f(1)\n    """\n',
            'def f():\n    """Do the thing.\n\n    Attributes:\n'
            '        name: A name.\n    """\n',
            'def f():\n    """Do the thing.\n\n    The check covers:\n\n'
            '    - one case\n    - another case\n    """\n',
            'def f():\n    """Do the thing.\n\n    Reads the config from:\n'
            '        pyproject.toml, walking upward.\n    """\n',
            'def f():\n    """Do the thing.\n\n    ```\n    Warns:\n'
            '        inside a fence\n    ```\n    """\n',
            'def f():\n    """Do the thing.\n\n    Raises:\n'
            '        PayloadError: If the check failed.\n            Wrapped.\n    """\n',
        ],
        ids=[
            "recognized-sections",
            "attributes-left-to-rs004",
            "colon-line-no-indented-body",
            "lowercase-words-not-header-shaped",
            "header-inside-fence",
            "indented-entry-caption-not-header",
        ],
    )
    def test_ConformingDocstring_NoViolation(self, source: str) -> None:
        assert list(check_invalid_docstring_section(_DOC_PATH, source)) == []

    def test_WarnsSection_FlagsAtHeader(self) -> None:
        source = (
            'def f():\n    """Verifies the dataset.\n\n    Raises:\n'
            "        PayloadError: If a check failed.\n\n    Warns:\n"
            '        RangeWarning: If a decode exceeds the range.\n    """\n'
        )
        violations = list(check_invalid_docstring_section(_DOC_PATH, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_INVALID_DOCSTRING_SECTION
        assert (violations[0].line, violations[0].col) == (7, 5)
        assert "'Warns:'" in violations[0].message

    @pytest.mark.parametrize(
        ("header", "body"),
        [
            ("Todo:", "drop the shim."),
            ("Keyword Args:", "extra: An extra."),
            ("Design Notes:", "The layout is deliberate."),
        ],
        ids=["napoleon-import", "two-word-napoleon", "invented-two-word"],
    )
    def test_UnrecognizedHeader_FlagsViolation(self, header: str, body: str) -> None:
        source = (
            f'def f():\n    """Do the thing.\n\n    {header}\n        {body}\n    """\n'
        )
        violations = list(check_invalid_docstring_section(_DOC_PATH, source))
        assert [(v.rule, v.line) for v in violations] == [
            (RS_INVALID_DOCSTRING_SECTION, 4)
        ]

    def test_ModuleDocstringWarns_FlagsAtHeader(self) -> None:
        source = '"""Do the module thing.\n\nWarns:\n    RangeWarning: Nope.\n"""\n'
        violations = list(check_invalid_docstring_section(_DOC_PATH, source))
        assert [(v.rule, v.line) for v in violations] == [
            (RS_INVALID_DOCSTRING_SECTION, 3)
        ]


class TestCheckDocstringSectionOrder:
    @pytest.mark.parametrize(
        "source",
        [
            'def f(x):\n    """Do the thing.\n\n    Args:\n'
            "        x: An x.\n\n    Returns:\n        The thing.\n\n"
            "    Raises:\n        ValueError: If x is bad.\n\n"
            '    Example:\n        >>> f(1)\n    """\n',
            'def f(x):\n    """Do the thing.\n\n    Args:\n'
            "        x: An x.\n\n    Yields:\n        Each thing.\n\n"
            '    Raises:\n        ValueError: If x is bad.\n    """\n',
            'def f():\n    """Do the thing.\n\n    Raises:\n'
            '        ValueError: If the input is bad.\n    """\n',
            'def f(x):\n    """Do the thing.\n\n    Note:\n        A note.\n\n'
            '    Args:\n        x: An x.\n    """\n',
        ],
        ids=[
            "canonical-order",
            "yields-in-returns-slot",
            "single-section",
            "note-unranked",
        ],
    )
    def test_ConformingOrder_NoViolation(self, source: str) -> None:
        assert list(check_docstring_section_order(_DOC_PATH, source)) == []

    def test_RaisesAboveReturns_FlagsAtReturns(self) -> None:
        source = (
            'def f():\n    """Do the thing.\n\n    Raises:\n'
            "        ValueError: If the input is bad.\n\n    Returns:\n"
            '        The thing.\n    """\n'
        )
        violations = list(check_docstring_section_order(_DOC_PATH, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_DOCSTRING_SECTION_ORDER
        assert (violations[0].line, violations[0].col) == (7, 5)
        assert "`Returns:` section sits below `Raises:`" in violations[0].message

    def test_ExampleAboveArgs_FlagsAtArgs(self) -> None:
        source = (
            'def f(x):\n    """Do the thing.\n\n    Example:\n'
            "        >>> f(1)\n\n    Args:\n"
            '        x: An x.\n    """\n'
        )
        violations = list(check_docstring_section_order(_DOC_PATH, source))
        assert [(v.rule, v.line) for v in violations] == [
            (RS_DOCSTRING_SECTION_ORDER, 7)
        ]

    def test_TwoSectionsBelowRaises_FlagsEach(self) -> None:
        source = (
            'def f(x):\n    """Do the thing.\n\n    Raises:\n'
            "        ValueError: If x is bad.\n\n    Args:\n"
            "        x: An x.\n\n    Returns:\n"
            '        The thing.\n    """\n'
        )
        violations = list(check_docstring_section_order(_DOC_PATH, source))
        assert [(v.rule, v.line) for v in violations] == [
            (RS_DOCSTRING_SECTION_ORDER, 7),
            (RS_DOCSTRING_SECTION_ORDER, 10),
        ]


class TestCheckDocstringSectionAlias:
    @pytest.mark.parametrize(
        "source",
        [
            'def f(x):\n    """Do the thing.\n\n    Args:\n'
            "        x: An x.\n\n    Returns:\n        The thing.\n\n"
            '    Yields:\n        Each thing.\n    """\n',
            'def f():\n    """Do the thing.\n\n    Notes:\n'
            '        Plural notes are not an alias.\n    """\n',
            'def f():\n    """Do the thing.\n\n    Examples:\n'
            '        >>> f()\n    """\n',
            'def f():\n    """Do the thing.\n\n    ```\n    Return:\n'
            '        inside a fence\n    ```\n    """\n',
            'def f():\n    """Do the thing.\n\n    Raises:\n'
            '        Return:\n            An indented entry caption.\n    """\n',
        ],
        ids=[
            "canonical-spellings",
            "plural-notes-not-alias",
            "plural-examples-not-alias",
            "alias-inside-fence",
            "indented-caption-not-header",
        ],
    )
    def test_ConformingDocstring_NoViolation(self, source: str) -> None:
        assert list(check_docstring_section_alias(_DOC_PATH, source)) == []

    @pytest.mark.parametrize(
        ("alias", "canonical"),
        [
            ("Arguments:", "Args:"),
            ("Return:", "Returns:"),
            ("Yield:", "Yields:"),
        ],
        ids=["arguments", "return", "yield"],
    )
    def test_AliasHeader_FlagsWithCanonical(self, alias: str, canonical: str) -> None:
        source = (
            f'def f(x):\n    """Do the thing.\n\n    {alias}\n'
            '        x: An x.\n    """\n'
        )
        violations = list(check_docstring_section_alias(_DOC_PATH, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_DOCSTRING_SECTION_ALIAS
        assert (violations[0].line, violations[0].col) == (4, 5)
        assert f"`{canonical}`" in violations[0].message


class TestCheckDuplicateDocstringSection:
    @pytest.mark.parametrize(
        "source",
        [
            'def f(x):\n    """Do the thing.\n\n    Args:\n'
            "        x: An x.\n\n    Returns:\n        The thing.\n\n"
            '    Raises:\n        ValueError: If x is bad.\n    """\n',
            'def f(x):\n    """Do the thing.\n\n    Returns:\n'
            '        The thing.\n\n    Yields:\n        Each thing.\n    """\n',
        ],
        ids=["one-of-each", "returns-and-yields-distinct-families"],
    )
    def test_ConformingDocstring_NoViolation(self, source: str) -> None:
        assert list(check_duplicate_docstring_section(_DOC_PATH, source)) == []

    def test_SecondArgsSection_FlagsAtDuplicate(self) -> None:
        source = (
            'def f(x, y):\n    """Do the thing.\n\n    Args:\n'
            "        x: An x.\n\n    Args:\n"
            '        y: A y.\n    """\n'
        )
        violations = list(check_duplicate_docstring_section(_DOC_PATH, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_DUPLICATE_DOCSTRING_SECTION
        assert (violations[0].line, violations[0].col) == (7, 5)

    def test_ArgsAfterArguments_FlagsAliasAsSameFamily(self) -> None:
        source = (
            'def f(x, y):\n    """Do the thing.\n\n    Arguments:\n'
            "        x: An x.\n\n    Args:\n"
            '        y: A y.\n    """\n'
        )
        violations = list(check_duplicate_docstring_section(_DOC_PATH, source))
        assert [(v.rule, v.line) for v in violations] == [
            (RS_DUPLICATE_DOCSTRING_SECTION, 7)
        ]
        assert "`Arguments:`" in violations[0].message

    def test_NotesAfterNote_FlagsAsSameFamily(self) -> None:
        source = (
            'def f():\n    """Do the thing.\n\n    Note:\n'
            "        A note.\n\n    Notes:\n"
            '        More notes.\n    """\n'
        )
        violations = list(check_duplicate_docstring_section(_DOC_PATH, source))
        assert [(v.rule, v.line) for v in violations] == [
            (RS_DUPLICATE_DOCSTRING_SECTION, 7)
        ]
