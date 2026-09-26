import sys
from pathlib import Path

import pytest

from repostyle.rules import (
    RS_GLUED_CODE_SPAN,
    RS_NO_DOUBLE_BACKTICKS,
    RS_UNBACKTICKED_CODE_REFERENCE,
    RS_UNBACKTICKED_SIBLING_SYMBOL,
    check_glued_code_span_in_comments,
    check_glued_code_span_in_docstrings,
    check_glued_code_span_in_md,
    check_no_double_backticks_in_docstrings,
    check_no_double_backticks_in_md,
    check_unbackticked_code_reference,
    check_unbackticked_sibling_symbol,
    check_unbackticked_sibling_symbol_in_comments,
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


class TestCheckNoDoubleBackticksInMd:
    def test_DoubleBackticksInProse_FlagsViolation(self) -> None:
        violations = list(
            check_no_double_backticks_in_md(
                Path("README.md"), "See ``ClassName`` for details."
            )
        )
        assert len(violations) == 1
        assert violations[0].rule == RS_NO_DOUBLE_BACKTICKS

    def test_DoubleBackticksMidLine_ColumnAtBacktickPair(self) -> None:
        violations = list(
            check_no_double_backticks_in_md(
                Path("README.md"), "See ``ClassName`` for details."
            )
        )
        assert (violations[0].line, violations[0].col) == (1, 5)

    @pytest.mark.parametrize(
        "source",
        [
            "See `ClassName` for details.",
            "```python\nx = 1\n```",
            "```python\n``not flagged``\n```",
        ],
        ids=["single", "fence-only", "double-inside-fence"],
    )
    def test_NoDoubleBackticksOutsideFences_NoViolation(self, source: str) -> None:
        assert list(check_no_double_backticks_in_md(Path("README.md"), source)) == []

    def test_NonMarkdownFile_NotChecked(self) -> None:
        assert (
            list(check_no_double_backticks_in_md(Path("README.txt"), "See ``X``."))
            == []
        )


class TestCheckNoDoubleBackticksInDocstrings:
    def test_DoubleBackticksInDocstring_FlagsViolation(self) -> None:
        violations = list(
            check_no_double_backticks_in_docstrings(
                Path("src/x.py"), '"""See ``ClassName`` for details."""'
            )
        )
        assert len(violations) == 1
        assert violations[0].rule == RS_NO_DOUBLE_BACKTICKS

    def test_SingleBackticksInDocstring_NoViolation(self) -> None:
        assert (
            list(
                check_no_double_backticks_in_docstrings(
                    Path("src/x.py"), '"""See `ClassName` for details."""'
                )
            )
            == []
        )


class TestCheckUnbacktickedCodeReference:
    @pytest.mark.parametrize(
        ("source", "token"),
        [
            ('def f() -> None:\n    """Returns None on a miss."""\n', "None"),
            (
                'def f(skip_lines):\n    """Drops skip_lines from the run."""\n',
                "skip_lines",
            ),
            (
                "from x import HttpClient\n\n\n"
                'def f():\n    """Builds a HttpClient."""\n',
                "HttpClient",
            ),
            (
                'def f(node):\n    """Reads node col_offset."""\n'
                "    return node.col_offset\n",
                "col_offset",
            ),
            (
                'def f(skip_lines):\n    """Does it. skip_lines drives it."""\n',
                "skip_lines",
            ),
            (
                'def f(skip_lines):\n    """Does it.\n\n'
                '    - drops skip_lines.\n    """\n',
                "skip_lines",
            ),
        ],
        ids=[
            "literal",
            "snake-case-param",
            "camel-case-import",
            "attribute",
            "code-shape-at-sentence-start",
            "bullet-item",
        ],
    )
    def test_BareCodeNameInProse_FlagsViolation(self, source: str, token: str) -> None:
        violations = list(check_unbackticked_code_reference(Path("src/x.py"), source))
        assert len(violations) == 1
        assert violations[0].rule == RS_UNBACKTICKED_CODE_REFERENCE
        assert f"`{token}`" in violations[0].message

    def test_BareLiteral_ColumnAtToken(self) -> None:
        source = 'def f() -> None:\n    """Returns None on a miss."""\n'
        violations = list(check_unbackticked_code_reference(Path("src/x.py"), source))
        assert (violations[0].line, violations[0].col) == (2, 16)

    @pytest.mark.parametrize(
        "source",
        [
            'def f() -> None:\n    """Returns `None` on a miss."""\n',
            'def f(path):\n    """Reads the path config."""\n',
            'def f() -> None:\n    """Does the thing. None marks a miss."""\n',
            'def f() -> None:\n    """Does it.\n\n    >>> f() is None\n    """\n',
            'def f(count):\n    """Returns the retry_budget as a count."""\n',
            'def f(skip_lines):\n    """Does it.\n\n'
            "    Args:\n        skip_lines: The lines to skip.\n    "
            '"""\n',
            'def f(config_path):\n    """Does it.\n\n'
            "    Args:\n        config_path (str): the path.\n    "
            '"""\n',
            'WARNING = 1\n\n\ndef f():\n    """Does it. WARNING resets state."""\n',
            'A = 1\n\n\ndef f():\n    """A result is returned."""\n',
            "class Note:\n    pass\n\n\n"
            'def f():\n    """Returns it. Please Note the order."""\n',
            'def f() -> None:\n    """See https://x.com/api/None here."""\n',
            'def f(skip_lines):\n    """Writes gs://bucket/skip_lines out."""\n',
        ],
        ids=[
            "backticked",
            "lowercase-english-word",
            "sentence-initial-literal",
            "doctest",
            "code-shaped-but-unbound",
            "args-caption",
            "typed-args-caption",
            "all-caps-english-at-sentence-start",
            "single-letter-name",
            "titlecase-english-word-mid-sentence",
            "name-inside-http-url",
            "name-inside-gs-uri",
        ],
    )
    def test_ConformingProse_NoViolation(self, source: str) -> None:
        assert list(check_unbackticked_code_reference(Path("src/x.py"), source)) == []

    def test_NonPythonFile_NotChecked(self) -> None:
        assert (
            list(check_unbackticked_code_reference(Path("README.md"), "Returns None."))
            == []
        )


class TestCheckUnbacktickedSiblingSymbol:
    def test_TableAndColumnBesideBacktickedClass_FlagsBoth(self) -> None:
        source = (
            '"""Bumps rows below the new floor.\n\n'
            "`ContinuousDiscoverySettings` now rejects a value, so a remote_aes\n"
            "row with continuous_min_study_age below it fails to construct; the\n"
            "remote_aes rows are bumped to the new floor.\n"
            '"""\n'
            "op.execute(\n"
            '    "UPDATE remote_aes SET continuous_min_study_age = 1"\n'
            ")\n"
        )
        violations = list(check_unbackticked_sibling_symbol(Path("src/x.py"), source))
        # `remote_aes` is named twice in the prose but flagged once, so the two
        # flags are one per distinct name, not one per mention.
        assert [violation.rule for violation in violations] == [
            RS_UNBACKTICKED_SIBLING_SYMBOL,
            RS_UNBACKTICKED_SIBLING_SYMBOL,
        ]
        flagged = " ".join(violation.message for violation in violations)
        assert "`remote_aes`" in flagged
        assert "`continuous_min_study_age`" in flagged

    def test_BoundNameSibling_LeftToRS036(self) -> None:
        source = (
            '"""Backticks `min_study_age`. Reads col_offset and remote_aes."""\n'
            "def f():\n"
            "    col_offset = 1\n"
            '    return f"UPDATE remote_aes SET min_study_age = {col_offset}"\n'
        )
        violations = list(check_unbackticked_sibling_symbol(Path("src/x.py"), source))
        assert len(violations) == 1
        assert "`remote_aes`" in violations[0].message

    @pytest.mark.parametrize(
        "source",
        [
            '"""Updates the remote_aes table."""\nx = "UPDATE remote_aes SET y = 1"\n',
            '"""Uses `remote_aes`. The status column drives it."""\n'
            'x = "UPDATE remote_aes SET status = 1"\n',
            '"""Uses `remote_aes` and `continuous_min_study_age`."""\n'
            'x = "UPDATE remote_aes SET continuous_min_study_age = 1"\n',
            '"""Uses `remote_aes`. Mentions some_other_field too."""\n'
            'x = "UPDATE remote_aes SET y = 1"\n',
            '"""Uses `status` here. Updates remote_aes too."""\n'
            'x = "UPDATE remote_aes SET y = 1"\n',
            '"""Bumps rows below the new floor.\n\n'
            "The remote_aes rows shift.\n\n"
            "Example:\n"
            "    x = `HttpClient`\n"
            '"""\n'
            'x = "UPDATE remote_aes SET y = 1"\n',
            '"""Imports study UIDs via `HttpClient`."""\nx = "load study UIDs"\n',
        ],
        ids=[
            "no-backticked-trigger",
            "plain-english-word-matching-string-token",
            "already-backticked-sibling",
            "distinctive-token-without-in-file-evidence",
            "backticked-word-is-not-a-code-symbol",
            "backtick-only-in-example-block",
            "pluralized-acronym-not-a-code-symbol",
        ],
    )
    def test_ConformingDocstring_NoViolation(self, source: str) -> None:
        assert list(check_unbackticked_sibling_symbol(Path("src/x.py"), source)) == []

    def test_NonPythonFile_NotChecked(self) -> None:
        source = '"""Uses `remote_aes`. Reads remote_aes."""\nx = "remote_aes"\n'
        assert list(check_unbackticked_sibling_symbol(Path("README.md"), source)) == []


class TestCheckUnbacktickedSiblingSymbolInComments:
    def test_TableBesideBacktickedClassInBlock_Flags(self) -> None:
        source = (
            "# `ContinuousDiscoverySettings` now rejects a value, so a\n"
            "# remote_aes row below the floor fails to load.\n"
            'op.execute("UPDATE remote_aes SET a = 1")\n'
        )
        violations = list(
            check_unbackticked_sibling_symbol_in_comments(Path("src/x.py"), source)
        )
        assert [violation.rule for violation in violations] == [
            RS_UNBACKTICKED_SIBLING_SYMBOL
        ]
        assert "`remote_aes`" in violations[0].message

    def test_BoundNameSibling_LeftToRS036(self) -> None:
        source = (
            "# Backticks `min_study_age`. Reads col_offset and remote_aes.\n"
            "def f():\n"
            "    col_offset = 1\n"
            '    return f"UPDATE remote_aes SET min_study_age = {col_offset}"\n'
        )
        violations = list(
            check_unbackticked_sibling_symbol_in_comments(Path("src/x.py"), source)
        )
        assert len(violations) == 1
        assert "`remote_aes`" in violations[0].message

    @pytest.mark.parametrize(
        "source",
        [
            '# Updates the remote_aes table.\nx = "UPDATE remote_aes SET y = 1"\n',
            "# Uses `remote_aes` and `min_study_age`.\n"
            'x = "UPDATE remote_aes SET min_study_age = 1"\n',
        ],
        ids=[
            "no-backticked-trigger",
            "already-backticked-sibling",
        ],
    )
    def test_ConformingComment_NoViolation(self, source: str) -> None:
        assert (
            list(
                check_unbackticked_sibling_symbol_in_comments(Path("src/x.py"), source)
            )
            == []
        )

    def test_TrailingComment_NotChecked(self) -> None:
        source = 'x = 1  # `HttpClient` beside bare_field\ny = "bare_field"\n'
        assert (
            list(
                check_unbackticked_sibling_symbol_in_comments(Path("src/x.py"), source)
            )
            == []
        )

    def test_NonPythonFile_NotChecked(self) -> None:
        source = "# Uses `remote_aes`. Reads remote_aes.\nx = 1\n"
        assert (
            list(check_unbackticked_sibling_symbol_in_comments(Path("x.toml"), source))
            == []
        )


class TestCheckGluedCodeSpanInDocstrings:
    @pytest.mark.parametrize(
        "docstring",
        [
            '"""Returns `patient.identifier`\'s value."""',
            '"""Returns the `Observation`s in the bundle."""',
            '"""Returns the bundle once `parse`d."""',
            # The curly apostrophe is the case under test, kept literal despite
            # RUF001's ambiguous-character warning.
            '"""Returns `x`’s value."""',  # noqa: RUF001
        ],
        ids=["possessive", "plural", "verb-suffix", "curly-apostrophe"],
    )
    def test_SuffixGluedToSpan_FlagsViolation(self, docstring: str) -> None:
        source = f"def f():\n    {docstring}\n"
        violations = list(check_glued_code_span_in_docstrings(Path("src/x.py"), source))
        assert len(violations) == 1
        assert violations[0].rule == RS_GLUED_CODE_SPAN

    @pytest.mark.parametrize(
        "docstring",
        [
            '"""Returns the value of `patient.identifier`."""',
            '"""Builds a `str`-typed value."""',
            '"""Returns `x`, then stops."""',
            '"""Returns `x` (the id)."""',
        ],
        ids=["of-form", "hyphen-compound", "punctuation", "paren"],
    )
    def test_SpanEndsOnWordBoundary_NoViolation(self, docstring: str) -> None:
        source = f"def f():\n    {docstring}\n"
        assert list(check_glued_code_span_in_docstrings(Path("src/x.py"), source)) == []

    def test_GluedSuffix_ColumnAtSuffix(self) -> None:
        source = 'def f():\n    """Uses `x`s here."""\n'
        violations = list(check_glued_code_span_in_docstrings(Path("src/x.py"), source))
        assert (violations[0].line, violations[0].col) == (2, 16)

    def test_TwoSpansWithGapBetween_NoViolation(self) -> None:
        # The gap between two spans must not be read as a span of its own, the
        # regression the finditer pairing exists to prevent.
        source = 'def f():\n    """Uses `a` and `b` here."""\n'
        assert list(check_glued_code_span_in_docstrings(Path("src/x.py"), source)) == []

    def test_TwoGluedSpans_FlagsEach(self) -> None:
        source = 'def f():\n    """Uses `a`s and `b`s here."""\n'
        violations = list(check_glued_code_span_in_docstrings(Path("src/x.py"), source))
        assert len(violations) == 2

    def test_GluedSuffixOnLaterLine_MapsToThatLineAndColumn(self) -> None:
        source = 'def f():\n    """Summary.\n\n    Uses `x`s in the body.\n    """\n'
        violations = list(check_glued_code_span_in_docstrings(Path("src/x.py"), source))
        assert (violations[0].line, violations[0].col) == (4, 13)

    def test_SpanCrossingLineBreak_NoFalsePositive(self) -> None:
        # A span whose backticks sit on different physical lines pairs as one
        # span; its trailing backtick must not pair with a later opening one.
        source = 'def f():\n    """Returns the `long\n    reference` value."""\n'
        assert list(check_glued_code_span_in_docstrings(Path("src/x.py"), source)) == []

    def test_EmptySpanBeforeLetter_NoViolation(self) -> None:
        source = 'def f():\n    """text ``s here."""\n'
        assert list(check_glued_code_span_in_docstrings(Path("src/x.py"), source)) == []

    def test_GluedSuffixInsideFence_NoViolation(self) -> None:
        # A fenced code block holds code, not prose; its backticks must not
        # pair with a prose span's and draw a false finding, as the Markdown
        # check also excludes a fence.
        source = (
            "def f():\n"
            '    """Doc.\n'
            "\n"
            "    ```\n"
            "    xs = `Observation`s\n"
            "    ```\n"
            '    """\n'
        )
        assert list(check_glued_code_span_in_docstrings(Path("src/x.py"), source)) == []

    def test_GluedSuffixInExampleSection_NoViolation(self) -> None:
        # An `Example:` section holds code, not prose, whether or not it is
        # fenced; the segmenter excludes it as it does for the other doc rules.
        source = (
            "def f():\n"
            '    """Parses input.\n'
            "\n"
            "    Example:\n"
            "        result = `parse`d output\n"
            '    """\n'
        )
        assert list(check_glued_code_span_in_docstrings(Path("src/x.py"), source)) == []

    def test_GluedSuffixInBullet_FlagsViolation(self) -> None:
        # A bullet item is prose, so a glued span in one is flagged, unlike a
        # code section; the finding lands on the bullet's own line.
        source = 'def f():\n    """Doc.\n\n    - uses `x`s here.\n    """\n'
        violations = list(check_glued_code_span_in_docstrings(Path("src/x.py"), source))
        assert (violations[0].line, violations[0].col) == (4, 15)

    def test_GluedSuffixInConcatenatedDocstring_FlagsViolation(self) -> None:
        # An implicitly-concatenated docstring collapses the value-to-physical
        # line mapping, so its lines are all scanned; the finding still lands
        # on the physical line the glued span sits on.
        source = 'def f():\n    ("""Summary text."""\n     """Uses `item`s here.""")\n'
        violations = list(check_glued_code_span_in_docstrings(Path("src/x.py"), source))
        assert (violations[0].line, violations[0].col) == (3, 20)

    def test_EscapedNewlineWithFence_NoViolation(self) -> None:
        # An escaped newline only adds value lines, not physical ones, so it is
        # not the collapsed-mapping case; the fence stays blanked, unscanned.
        source = (
            "def f():\n"
            '    """Doc.\\nmore.\n'
            "\n"
            "    ```\n"
            "    y = `item`s\n"
            "    ```\n"
            '    """\n'
        )
        assert list(check_glued_code_span_in_docstrings(Path("src/x.py"), source)) == []


class TestCheckGluedCodeSpanInComments:
    def test_SuffixGluedToSpanInComment_FlagsViolation(self) -> None:
        source = "x = 1  # `retries`'s ceiling\n"
        violations = list(check_glued_code_span_in_comments(Path("src/x.py"), source))
        assert len(violations) == 1
        assert violations[0].rule == RS_GLUED_CODE_SPAN

    def test_SpanEndsOnWordBoundaryInComment_NoViolation(self) -> None:
        source = "x = 1  # the ceiling of `retries`\n"
        assert list(check_glued_code_span_in_comments(Path("src/x.py"), source)) == []

    def test_GluedSuffixInComment_ColumnAtSuffix(self) -> None:
        source = "x = 1  # `retries`'s ceiling\n"
        violations = list(check_glued_code_span_in_comments(Path("src/x.py"), source))
        assert (violations[0].line, violations[0].col) == (1, 19)

    def test_YamlComment_FlagsViolation(self) -> None:
        source = "key: 1  # `retries`'s cap\n"
        violations = list(check_glued_code_span_in_comments(Path("cfg.yaml"), source))
        assert len(violations) == 1
        assert violations[0].rule == RS_GLUED_CODE_SPAN

    def test_MarkdownFile_NotCheckedAsComment(self) -> None:
        # `.md` is not a comment-bearing suffix; a heading is the md check's,
        # not the comment check's, so it is not tokenized or double-reported.
        source = "# `Observation`s heading\n"
        assert list(check_glued_code_span_in_comments(Path("README.md"), source)) == []

    def test_MalformedPythonIndentation_DoesNotRaise(self) -> None:
        # An untokenizable file yields nothing rather than aborting the run;
        # the finding on the malformed line is dropped, not reported.
        source = "def f():\n    x = 1\n  y = 2  # `x`'s note\n"
        assert list(check_glued_code_span_in_comments(Path("bad.py"), source)) == []


class TestCheckGluedCodeSpanInMd:
    def test_SuffixGluedToSpanInMd_FlagsViolation(self) -> None:
        violations = list(
            check_glued_code_span_in_md(Path("README.md"), "The `Observation`s ship.")
        )
        assert len(violations) == 1
        assert violations[0].rule == RS_GLUED_CODE_SPAN

    def test_GluedSuffixInsideFence_NoViolation(self) -> None:
        source = "```python\nxs = `Observation`s\n```"
        assert list(check_glued_code_span_in_md(Path("README.md"), source)) == []

    def test_SpanAtEndOfLine_NoViolation(self) -> None:
        assert (
            list(check_glued_code_span_in_md(Path("README.md"), "See `Observation`"))
            == []
        )

    def test_NonMarkdownFile_NotChecked(self) -> None:
        assert (
            list(check_glued_code_span_in_md(Path("notes.txt"), "The `Observation`s."))
            == []
        )
