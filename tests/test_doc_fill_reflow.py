from pathlib import Path

import pytest

from repostyle.rules.doc_fill import check_doc_fill, reflow_doc_fill

_PY = Path("src/x.py")
_MOVES_WHOLE = '"""Summary.\n\n' + "aaaaa " * 11 + "`dict[str, int]` done.\n" + '"""\n'
_OVERFLOWS = '"""Summary.\n\n`' + "word " * 16 + 'x`\n"""\n'


class TestReflowDocFill:
    def test_UnderwrappedParagraph_JoinsToLimit(self) -> None:
        source = 'def f():\n    """Summary.\n\n    aaa\n    bbb\n    """\n'
        assert reflow_doc_fill(_PY, source) == (
            'def f():\n    """Summary.\n\n    aaa bbb\n    """\n'
        )

    def test_OverlongParagraph_SplitsAtLimit(self) -> None:
        source = '"""Summary.\n\n' + "abcde " * 13 + 'end.\n"""\n'
        rewritten = reflow_doc_fill(_PY, source)
        body = rewritten.splitlines()[2:-1]
        assert all(len(line) <= 79 for line in body)
        assert len(body) > 1

    def test_GoogleSectionEntry_WrapsAsHangingIndent(self) -> None:
        source = (
            'def f(alpha):\n    """Summary.\n\n'
            "    Args:\n        alpha: " + "word " * 20 + "end.\n"
            '    """\n'
        )
        body = reflow_doc_fill(_PY, source).splitlines()
        entry = next(i for i, line in enumerate(body) if "alpha:" in line)
        assert body[entry].startswith("        alpha:")
        assert body[entry + 1].startswith("            ")

    def test_Bullet_WrapsUnderMarker(self) -> None:
        source = '"""Summary.\n\n- ' + "word " * 20 + 'end.\n"""\n'
        body = reflow_doc_fill(_PY, source).splitlines()
        assert body[2].startswith("- ")
        assert body[3].startswith("  ") and not body[3].startswith("   ")

    def test_Comment_JoinsToLimit(self) -> None:
        source = "# aaa\n# bbb\nx = 1\n"
        assert reflow_doc_fill(_PY, source) == "# aaa bbb\nx = 1\n"

    def test_FlagLikeProseLine_IsFilledNotTreatedAsVerbatim(self) -> None:
        source = '"""Summary.\n\naaa\n--fix bbb\n"""\n'
        assert reflow_doc_fill(_PY, source) == '"""Summary.\n\naaa --fix bbb\n"""\n'

    @pytest.mark.parametrize(
        ("source", "span"),
        [
            (_MOVES_WHOLE, "`dict[str, int]`"),
            (_OVERFLOWS, "`" + "word " * 16 + "x`"),
        ],
        ids=["moves_whole_to_next_line", "overflows_intact"],
    )
    def test_BacktickSpanWithSpaces_StaysOneToken(self, source: str, span: str) -> None:
        body = reflow_doc_fill(_PY, source).splitlines()[2:-1]
        assert span in "\n".join(body)
        assert any(line.startswith(span) for line in body)

    def test_UnclosedBacktick_SplitsOnWhitespaceAlone(self) -> None:
        source = '"""Summary.\n\naaa `dict[str, int and more text here\n"""\n'
        assert reflow_doc_fill(_PY, source) == source

    def test_SpanHardWrappedAcrossLines_LeavesUnitUntouched(self) -> None:
        source = (
            '"""Summary.\n\n'
            "It mirrors ruff's `too-many-positional-\n"
            'arguments` semantics here.\n"""\n'
        )
        assert reflow_doc_fill(_PY, source) == source

    @pytest.mark.parametrize(
        "source", [_MOVES_WHOLE, _OVERFLOWS], ids=["moves_whole", "overflows"]
    )
    def test_ReflowedBacktickSpan_LeavesNoCheckViolation(self, source: str) -> None:
        assert list(check_doc_fill(_PY, reflow_doc_fill(_PY, source))) == []

    def test_CarriageReturnNewlines_ArePreserved(self) -> None:
        source = 'def f():\r\n    """Summary.\r\n\r\n    aaa\r\n    bbb\r\n    """\r\n'
        rewritten = reflow_doc_fill(_PY, source)
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
        assert reflow_doc_fill(_PY, source) == source

    def test_InlineClosingQuote_SkipsUnit(self) -> None:
        source = '"""Summary.\n\naaa\nbbb"""\n'
        assert reflow_doc_fill(_PY, source) == source

    def test_SkipLine_LeavesUnitUntouched(self) -> None:
        source = 'def f():\n    """Summary.\n\n    aaa\n    bbb\n    """\n'
        assert reflow_doc_fill(_PY, source, frozenset({4})) == source

    def test_NonPythonFile_ReturnsUnchanged(self) -> None:
        source = "aaa\nbbb\n"
        assert reflow_doc_fill(Path("README.md"), source) == source
