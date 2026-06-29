from pathlib import Path

import pytest

from pystyle.rules import (
    check_comment_terminal_punctuation,
    check_docstring_terminal_punctuation,
    check_no_double_backticks_in_docstrings,
    check_no_double_backticks_in_md,
    fix_comment_terminal_punctuation,
    fix_docstring_terminal_punctuation,
    fix_double_backticks,
)
from pystyle.runner import fix_path

_PY = Path("src/x.py")
_MD = Path("README.md")


def _project(tmp_path: Path, source: str, select: str, name: str = "x.py") -> Path:
    (tmp_path / "pyproject.toml").write_text(
        f"[tool.pystyle]\nselect = {select}\n", encoding="utf-8"
    )
    target = tmp_path / name
    target.write_text(source, encoding="utf-8")
    return target


class TestFixDoubleBackticks:
    def test_DocstringDoubleBackticks_RewriteToSingle(self) -> None:
        source = 'def f():\n    """Use ``dict`` here."""\n'
        assert fix_double_backticks(_PY, source) == (
            'def f():\n    """Use `dict` here."""\n'
        )

    def test_MarkdownProse_RewriteToSingle(self) -> None:
        assert fix_double_backticks(_MD, "See ``X`` now.\n") == "See `X` now.\n"

    def test_MarkdownFencedBlock_LeftUntouched(self) -> None:
        source = "Use ``x``.\n\n```\ncode ``y``\n```\n"
        assert fix_double_backticks(_MD, source) == "Use `x`.\n\n```\ncode ``y``\n```\n"

    def test_TripleBackticks_LeftUntouched(self) -> None:
        source = 'def f():\n    """A ```fence``` token."""\n'
        assert fix_double_backticks(_PY, source) == source

    def test_OwnerLineSuppressed_LeavesDocstring(self) -> None:
        source = 'def f():  # style: ignore[RS005]\n    """Use ``dict``."""\n'
        assert fix_double_backticks(_PY, source, frozenset({1})) == source

    def test_NoDoubleBackticks_ReturnsSourceUnchanged(self) -> None:
        source = 'def f():\n    """Use `dict` here."""\n'
        assert fix_double_backticks(_PY, source) == source

    def test_FixedDocstring_ClearsTheRule(self) -> None:
        source = 'def f():\n    """Use ``dict`` here."""\n'
        fixed = fix_double_backticks(_PY, source)
        assert list(check_no_double_backticks_in_docstrings(_PY, fixed)) == []

    def test_FixedMarkdown_ClearsTheRule(self) -> None:
        fixed = fix_double_backticks(_MD, "See ``X`` now.\n")
        assert list(check_no_double_backticks_in_md(_MD, fixed)) == []


class TestFixDocstringTerminalPunctuation:
    def test_SingleLineSummary_AppendsPeriodBeforeQuote(self) -> None:
        assert fix_docstring_terminal_punctuation(_PY, '"""Resolve the lease"""\n') == (
            '"""Resolve the lease."""\n'
        )

    def test_BodyParagraph_AppendsPeriodOnLastLine(self) -> None:
        source = 'def f():\n    """Do it.\n\n    The body has no mark\n    """\n'
        assert fix_docstring_terminal_punctuation(_PY, source) == (
            'def f():\n    """Do it.\n\n    The body has no mark.\n    """\n'
        )

    def test_SectionEntry_AppendsPeriod(self) -> None:
        source = (
            'def f(a):\n    """Summary.\n\n    Args:\n        a: the thing\n    """\n'
        )
        assert fix_docstring_terminal_punctuation(_PY, source) == (
            'def f(a):\n    """Summary.\n\n    Args:\n        a: the thing.\n    """\n'
        )

    def test_UnitEndingInCloser_AppendsAfterCloser(self) -> None:
        source = 'def f():\n    """See the note (here)"""\n'
        assert fix_docstring_terminal_punctuation(_PY, source) == (
            'def f():\n    """See the note (here)."""\n'
        )

    def test_NonAsciiClosingLine_InsertsBeforeQuoteNotPastIt(self) -> None:
        source = 'def f():\n    """Résumé café text"""\n'
        assert fix_docstring_terminal_punctuation(_PY, source) == (
            'def f():\n    """Résumé café text."""\n'
        )

    def test_LineSuppressed_LeavesUnit(self) -> None:
        source = '"""Resolve the lease"""\n'
        assert fix_docstring_terminal_punctuation(_PY, source, frozenset({1})) == source

    def test_AlreadyTerminated_ReturnsSourceUnchanged(self) -> None:
        source = '"""Resolve the lease."""\n'
        assert fix_docstring_terminal_punctuation(_PY, source) == source

    def test_FixedSummary_ClearsTheRule(self) -> None:
        fixed = fix_docstring_terminal_punctuation(_PY, '"""Resolve the lease"""\n')
        assert list(check_docstring_terminal_punctuation(_PY, fixed)) == []


class TestFixCommentTerminalPunctuation:
    def test_ProseBlockMissingMark_AppendsPeriod(self) -> None:
        source = "# This is prose spanning\n# two lines here\nx = 1\n"
        assert fix_comment_terminal_punctuation(_PY, source) == (
            "# This is prose spanning\n# two lines here.\nx = 1\n"
        )

    def test_TrailingFragmentWithPeriod_DropsIt(self) -> None:
        source = "x = 1  # Frobnicate the widget here.\n"
        assert fix_comment_terminal_punctuation(_PY, source) == (
            "x = 1  # Frobnicate the widget here\n"
        )

    def test_FragmentPeriodBeforeCloser_DropsPeriodKeepsCloser(self) -> None:
        source = "x = 1  # Frobnicate the widget (here.)\n"
        fixed = fix_comment_terminal_punctuation(_PY, source)
        assert fixed == "x = 1  # Frobnicate the widget (here)\n"
        assert list(check_comment_terminal_punctuation(_PY, fixed)) == []

    def test_LineSuppressed_LeavesComment(self) -> None:
        source = "x = 1  # Frobnicate the widget here.\n"
        assert fix_comment_terminal_punctuation(_PY, source, frozenset({1})) == source

    def test_MarkdownPath_ReturnsSourceUnchanged(self) -> None:
        assert (
            fix_comment_terminal_punctuation(_MD, "# Title here\n") == "# Title here\n"
        )

    def test_FixedBlock_ClearsTheRule(self) -> None:
        source = "# This is prose spanning\n# two lines here\nx = 1\n"
        fixed = fix_comment_terminal_punctuation(_PY, source)
        assert list(check_comment_terminal_punctuation(_PY, fixed)) == []


class TestFixPath:
    def test_EnabledFixers_ComposeOnOneFile(self, tmp_path: Path) -> None:
        source = (
            'def f():\n    """Use ``dict`` here\n\n'
            '    The body line has no mark\n    """\n'
        )
        target = _project(tmp_path, source, '["RS005", "RS009", "RS030"]')
        assert fix_path(target, {"RS005", "RS009", "RS030"}) is True
        assert target.read_text(encoding="utf-8") == (
            'def f():\n    """Use `dict` here.\n\n'
            '    The body line has no mark.\n    """\n'
        )

    def test_OnlyOneRuleEnabled_LeavesTheOthers(self, tmp_path: Path) -> None:
        source = 'def f():\n    """Use ``dict`` here"""\n'
        target = _project(tmp_path, source, '["RS005"]')
        fix_path(target, {"RS005"})
        assert target.read_text(encoding="utf-8") == (
            'def f():\n    """Use `dict` here"""\n'
        )

    def test_MarkdownFile_FixesBackticksOnly(self, tmp_path: Path) -> None:
        target = _project(tmp_path, "See ``X``.\n", '["RS005"]', name="README.md")
        assert fix_path(target, {"RS005"}) is True
        assert target.read_text(encoding="utf-8") == "See `X`.\n"

    def test_FileLevelIgnore_LeavesFileUntouched(self, tmp_path: Path) -> None:
        source = '# style: ignore-file\ndef f():\n    """Use ``dict``"""\n'
        target = _project(tmp_path, source, '["RS005", "RS030"]')
        assert fix_path(target, {"RS005", "RS030"}) is False
        assert target.read_text(encoding="utf-8") == source

    def test_NoEnabledFixableRule_NoOp(self, tmp_path: Path) -> None:
        source = 'def f():\n    """Use ``dict``"""\n'
        target = _project(tmp_path, source, '["RS001"]')
        assert fix_path(target, {"RS001"}) is False
        assert target.read_text(encoding="utf-8") == source

    @pytest.mark.parametrize("suffix", [".txt", ".cfg", ".toml"])
    def test_NonSourceSuffix_NoOp(self, tmp_path: Path, suffix: str) -> None:
        target = _project(tmp_path, "See ``X``.\n", '["RS005"]', name=f"data{suffix}")
        assert fix_path(target, {"RS005"}) is False
