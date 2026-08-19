from pathlib import Path

import pytest

from repostyle.rules.doc_fill import DOC_FILL_COLUMNS, check_doc_fill, fix_doc_fill

_PY = Path("src/x.py")
_SHELL = Path("deploy/bootstrap.sh")
_MOVES_WHOLE = '"""Summary.\n\n' + "aaaaa " * 11 + "`dict[str, int]` done.\n" + '"""\n'
_OVERFLOWS = '"""Summary.\n\n`' + "word " * 16 + 'x`\n"""\n'
# A copyable command whose `\` continuations carry the line breaks, and a
# two-column settings list whose interior padding carries the alignment.
_LINE_CONTINUATIONS = (
    "#        [--setenv=HTTP_PROXY=http://proxy:3128] \\\n"
    "#        [--setenv=NO_PROXY=localhost,127.0.0.1] \\\n"
    "#        ./bootstrap.sh\n"
)
_ALIGNED_LIST = (
    "# Reads its settings from /etc/reconciler/reconcile.env:\n"
    "#   RELEASE_URI   gs:// prefix the deploy workflow publishes to\n"
    "#   COMPOSE_DIR   directory holding docker-compose.yaml, env, and .env.local\n"
    "#   ENVIRONMENT   environment name, for the beacon\n"
    "#   BEACON_LOG    Cloud Logging log name for the deploy beacon\n"
)
# Prose spaced two-per-sentence, the convention the preformatted test has to
# stay clear of: an alignment gap is wider, so this is a paragraph.
_TWO_SPACE_SENTENCES = (
    "# This sentence ends here.  And this one runs well past the limit, so the"
    " rule has something to report.\n"
)
# A tab-indented block from a shell script, each line inside 79 characters but
# past the limit once the tab reaches its stop.
_TAB_INDENTED = (
    "\t# here on a re-run. Only worth saying when a source was actually named: a\n"
    "\t# run that omitted it has the destination itself missing, which is the\n"
    "\t# first-run case above.\n"
)


class TestReflowDocFill:
    def test_UnderwrappedParagraph_JoinsToLimit(self) -> None:
        source = 'def f():\n    """Summary.\n\n    aaa\n    bbb\n    """\n'
        assert fix_doc_fill(_PY, source) == (
            'def f():\n    """Summary.\n\n    aaa bbb\n    """\n'
        )

    def test_OverlongParagraph_SplitsAtLimit(self) -> None:
        source = '"""Summary.\n\n' + "abcde " * 13 + 'end.\n"""\n'
        rewritten = fix_doc_fill(_PY, source)
        body = rewritten.splitlines()[2:-1]
        assert all(len(line) <= 79 for line in body)
        assert len(body) > 1

    def test_GoogleSectionEntry_WrapsAsHangingIndent(self) -> None:
        source = (
            'def f(alpha):\n    """Summary.\n\n'
            "    Args:\n        alpha: " + "word " * 20 + "end.\n"
            '    """\n'
        )
        body = fix_doc_fill(_PY, source).splitlines()
        entry = next(i for i, line in enumerate(body) if "alpha:" in line)
        assert body[entry].startswith("        alpha:")
        assert body[entry + 1].startswith("            ")

    def test_Bullet_WrapsUnderMarker(self) -> None:
        source = '"""Summary.\n\n- ' + "word " * 20 + 'end.\n"""\n'
        body = fix_doc_fill(_PY, source).splitlines()
        assert body[2].startswith("- ")
        assert body[3].startswith("  ")
        assert not body[3].startswith("   ")

    def test_Comment_JoinsToLimit(self) -> None:
        source = "# aaa\n# bbb\nx = 1\n"
        assert fix_doc_fill(_PY, source) == "# aaa bbb\nx = 1\n"

    def test_FlagLikeProseLine_IsFilledNotTreatedAsVerbatim(self) -> None:
        source = '"""Summary.\n\naaa\n--fix bbb\n"""\n'
        assert fix_doc_fill(_PY, source) == '"""Summary.\n\naaa --fix bbb\n"""\n'

    @pytest.mark.parametrize(
        ("source", "span"),
        [
            (_MOVES_WHOLE, "`dict[str, int]`"),
            (_OVERFLOWS, "`" + "word " * 16 + "x`"),
        ],
        ids=["moves_whole_to_next_line", "overflows_intact"],
    )
    def test_BacktickSpanWithSpaces_StaysOneToken(self, source: str, span: str) -> None:
        body = fix_doc_fill(_PY, source).splitlines()[2:-1]
        assert span in "\n".join(body)
        assert any(line.startswith(span) for line in body)

    def test_UnclosedBacktick_SplitsOnWhitespaceAlone(self) -> None:
        source = '"""Summary.\n\naaa `dict[str, int and more text here\n"""\n'
        assert fix_doc_fill(_PY, source) == source

    def test_SpanHardWrappedAcrossLines_LeavesUnitUntouched(self) -> None:
        source = (
            '"""Summary.\n\n'
            "It mirrors ruff's `too-many-positional-\n"
            'arguments` semantics here.\n"""\n'
        )
        assert fix_doc_fill(_PY, source) == source

    @pytest.mark.parametrize(
        "source", [_MOVES_WHOLE, _OVERFLOWS], ids=["moves_whole", "overflows"]
    )
    def test_ReflowedBacktickSpan_LeavesNoCheckViolation(self, source: str) -> None:
        assert list(check_doc_fill(_PY, fix_doc_fill(_PY, source))) == []

    def test_CarriageReturnNewlines_ArePreserved(self) -> None:
        source = 'def f():\r\n    """Summary.\r\n\r\n    aaa\r\n    bbb\r\n    """\r\n'
        rewritten = fix_doc_fill(_PY, source)
        assert "    aaa bbb\r\n" in rewritten
        assert rewritten.count("\n") == rewritten.count("\r\n")

    @pytest.mark.parametrize(
        "source",
        [
            'def f():\n    """Summary.\n\n    A single filled body line.\n    """\n',
            '"""Summary.\n\n| a | b |\n| - | - |\n"""\n',
            '"""Summary.\n\n+---+\n| x |\n+---+\n"""\n',
            '"""Summary.\n\n```\nx=1\nif y:pass\n```\n"""\n',
            '"""Summary.\n\n>>> f( 1 )\n2\n"""\n',
        ],
        ids=[
            "already_filled",
            "markdown_table",
            "ascii_diagram",
            "fenced_code",
            "doctest",
        ],
    )
    def test_FilledOrVerbatimContent_ReturnsUnchanged(self, source: str) -> None:
        assert fix_doc_fill(_PY, source) == source

    @pytest.mark.parametrize(
        "source",
        [_LINE_CONTINUATIONS, _ALIGNED_LIST],
        ids=["line_continuations", "aligned_list"],
    )
    def test_PreformattedComment_ReturnsUnchanged(self, source: str) -> None:
        assert fix_doc_fill(_SHELL, source) == source

    def test_TwoSpaceSentenceSpacing_StaysProse(self) -> None:
        """Sentence spacing must not read as an alignment and exempt the unit.

        The preformatted test is what keeps a continuation or a column gap out
        of the reflow, and a run of two spaces after a full stop is neither.
        Counting it as one would take every paragraph in a codebase spaced that
        way out of the rule's reach, reporting nothing on any of them.
        """
        assert list(check_doc_fill(_SHELL, _TWO_SPACE_SENTENCES))
        assert fix_doc_fill(_SHELL, _TWO_SPACE_SENTENCES) != _TWO_SPACE_SENTENCES

    @pytest.mark.parametrize(
        "source",
        [
            '"""Summary.\n\nSee https://example.com/' + "a" * 60 + '\n"""\n',
            '"""Summary.\n\n' + "a" * 80 + ' bb\n"""\n',
        ],
        ids=["url_line", "unbreakable_token"],
    )
    def test_UnflaggedUnit_ReturnsUnchanged(self, source: str) -> None:
        assert list(check_doc_fill(_PY, source)) == []
        assert fix_doc_fill(_PY, source) == source

    def test_TabIndentedComment_EmitsNoLinePastLimit(self) -> None:
        rewritten = fix_doc_fill(_SHELL, _TAB_INDENTED)
        assert rewritten != _TAB_INDENTED
        # `expandtabs` with no argument is the same tab stop a terminal uses.
        widths = [len(line.expandtabs()) for line in rewritten.splitlines()]
        assert max(widths) <= DOC_FILL_COLUMNS

    def test_InlineClosingQuote_SkipsUnit(self) -> None:
        source = '"""Summary.\n\naaa\nbbb"""\n'
        assert fix_doc_fill(_PY, source) == source

    def test_SkipLine_LeavesUnitUntouched(self) -> None:
        source = 'def f():\n    """Summary.\n\n    aaa\n    bbb\n    """\n'
        assert fix_doc_fill(_PY, source, frozenset({4})) == source

    def test_NonPythonFile_ReturnsUnchanged(self) -> None:
        source = "aaa\nbbb\n"
        assert fix_doc_fill(Path("README.md"), source) == source
