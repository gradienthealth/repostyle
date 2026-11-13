from pathlib import Path

import pytest

from repostyle.rules import RS_STRING_FILL
from repostyle.rules.doc_fill import check_string_fill, fix_string_fill

_PY = Path("src/x.py")

_UNDERWRAPPED = (
    "raise ValueError(\n"
    '    "Every selected project needs a reviewed policy folder before "\n'
    '    "it can be requested with other projects."\n'
    ")\n"
)
_FILLED = (
    "raise ValueError(\n"
    '    "Every selected project needs a reviewed policy folder before it can be "\n'
    '    "requested with other projects."\n'
    ")\n"
)
_OVERFLOWING = (
    "message = (\n"
    '    "The author resolves an ack by quote-replying the comment on GitHub, or "\n'
    '    "with the Acknowledge button under it in the Slack thread, which is slower."\n'
    ")\n"
)
_PLACEHOLDERS = (
    "message = (\n"
    '    f"except catches {listed} together; each says a value was not the "\n'
    '    f"shape the code assumed, so raise a named error where {where} is "\n'
    '    f"decided and narrow this handler to {{it}}."\n'
    ")\n"
)


class TestCheckStringFill:
    def test_FilledRun_PassesClean(self) -> None:
        assert list(check_string_fill(_PY, _FILLED)) == []

    def test_UnderwrappedRun_FlagsFirstShortLine(self) -> None:
        [violation] = check_string_fill(_PY, _UNDERWRAPPED)
        assert (violation.rule, violation.line) == (RS_STRING_FILL, 2)
        assert "'it' still fits" in violation.message

    def test_OverflowingRun_FlagsLongLine(self) -> None:
        [violation] = check_string_fill(_PY, _OVERFLOWING)
        assert (violation.rule, violation.line) == (RS_STRING_FILL, 3)
        assert "runs past 79 columns" in violation.message

    @pytest.mark.parametrize(
        "source",
        [
            'query = (\n    "SELECT a, b "\n    "FROM t "\n    "WHERE c = 1"\n)\n',
            'html = (\n    "<p>Short line. "\n    "Another.</p>."\n)\n',
            'pattern = (\n    r"a raw "\n    r"pattern."\n)\n',
            'text = (\n    "first half, "\n    # a comment\n    "second."\n)\n',
            'text = (\n    "two  spaces "\n    "here."\n)\n',
            'text = (\n    "joined"\n    " mid-word."\n)\n',
            '"""Docstring\nspread over lines."""\n',
            'text = """triple\nquoted body."""\n',
        ],
        ids=[
            "unpunctuated",
            "html",
            "raw",
            "comment",
            "double-space",
            "leading-space",
            "docstring",
            "triple-quoted",
        ],
    )
    def test_NonProseRun_IsIgnored(self, source: str) -> None:
        assert list(check_string_fill(_PY, source)) == []


class TestFixStringFill:
    def test_UnderwrappedRun_RewrapsToFilled(self) -> None:
        assert fix_string_fill(_PY, _UNDERWRAPPED) == _FILLED

    def test_OverflowingRun_SplitsWithinLimit(self) -> None:
        fixed = fix_string_fill(_PY, _OVERFLOWING)
        assert max(len(line) for line in fixed.splitlines()) <= 79
        assert list(check_string_fill(_PY, fixed)) == []

    def test_PlaceholderRun_KeepsValueAndDropsUnusedPrefix(self) -> None:
        fixed = fix_string_fill(_PY, _PLACEHOLDERS)
        assert _value(fixed) == _value(_PLACEHOLDERS)
        assert fixed.splitlines()[3] == '    "narrow this handler to {it}."'

    @pytest.mark.parametrize(
        "source",
        [
            'message = (\n    "Hello there. "\n    "Short and done. "\n) + "x"\n',
            "message = (\n"
            '    "aaaa aaaa aaaa aaaa aaaa aaaa aaaa aaaa aaaa aaaa aaaa aaaa x "\n'
            '    "\\N{EM DASH} is the dash we want here."\n'
            ")\n",
            'message = (\n    "Use {braces} in "\n    f"{listed} here."\n)\n',
            'message = (\n    f"Value {\'}\'} is "\n    f"here."\n)\n',
            'message = (\n    "Hello world. "\n    ""\n)\n',
        ],
        ids=[
            "trailing-space",
            "named-escape",
            "literal-braces",
            "quoted-brace",
            "empty-last",
        ],
    )
    def test_EdgeRun_KeepsValueAndPassesRecheck(self, source: str) -> None:
        fixed = fix_string_fill(_PY, source)
        assert _value(fixed) == _value(source)
        assert list(check_string_fill(_PY, fixed)) == []

    def test_TrailingCode_StaysOnLastLine(self) -> None:
        source = (
            "call(\n"
            '    "Every selected project needs a reviewed policy folder before "\n'
            '    "it can be requested with other projects.", stacklevel=2\n'
            ")\n"
        )
        assert fix_string_fill(_PY, source).splitlines()[2] == (
            '    "requested with other projects.", stacklevel=2'
        )

    def test_SkippedLine_LeavesRunAlone(self) -> None:
        assert fix_string_fill(_PY, _UNDERWRAPPED, frozenset({3})) == _UNDERWRAPPED


def _value(source: str) -> object:
    namespace = {"listed": "ValueError", "where": "that"}
    exec(source, namespace)
    return namespace["message"]
