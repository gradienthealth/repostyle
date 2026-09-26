import sys
from pathlib import Path

import pytest

from repostyle.rules import (
    RS_BANNER_COMMENT,
    RS_DOUBLE_SPACE_AFTER_PERIOD,
    check_banner_comment,
    check_double_space_after_period,
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


class TestCheckBannerComment:
    @pytest.mark.parametrize(
        "source",
        [
            "# ---\nx = 1\n",
            "# +----+\n# | a  |\n# +----+\nx = 1\n",
            "x = 1  # ----\n",
            "x = 1  # --- main ---\n",
            "# A plain prose comment.\nx = 1\n",
            "# -*- coding: utf-8 -*-\nx = 1\n",
            "# ---8<--- cut here\nx = 1\n",
            "# -----> the retry path\nx = 1\n",
            "## note on the constant\nx = 1\n",
        ],
        ids=[
            "three-dashes",
            "ascii-table-border",
            "trailing-divider",
            "trailing-framed-title",
            "prose",
            "coding-declaration",
            "scissors",
            "arrow",
            "comment-level",
        ],
    )
    def test_ConformingComment_NoViolation(self, source: str) -> None:
        assert list(check_banner_comment(_DOC_PATH, source)) == []

    @pytest.mark.parametrize(
        "comment",
        [
            "# --- see the note below",
            "# === TESTS ===",
            "# ---------- main ----------",
            "# --- Main ---",
            "# --- Main event loop",
            "# -------- Export Service Tables  ------------",
            "# Bucket names ----------",
            "# --- coding: the encoding step ---",
        ],
        ids=[
            "half-frame",
            "decorated-one-line-title",
            "padded",
            "tight",
            "unclosed",
            "ragged",
            "trailing-frame",
            "says-coding",
        ],
    )
    def test_FramedTitle_FlagsWhateverItsShape(self, comment: str) -> None:
        violations = list(check_banner_comment(_DOC_PATH, f"{comment}\nx = 1\n"))
        assert [v.rule for v in violations] == [RS_BANNER_COMMENT]

    @pytest.mark.parametrize(
        "line",
        ["# -----", "#####", "# ====", "# ~~~~", "# ____", "# ****"],
        ids=["dashes", "hashes", "equals", "tildes", "underscores", "stars"],
    )
    def test_DividerLine_Flags(self, line: str) -> None:
        violations = list(check_banner_comment(_DOC_PATH, f"{line}\nx = 1\n"))
        assert [(v.rule, v.line, v.col) for v in violations] == [
            (RS_BANNER_COMMENT, 1, 1)
        ]
        assert "banner" in violations[0].message

    def test_FramedBanner_FlagsEachFrameLine(self) -> None:
        source = "# -----------\n# TESTS\n# -----------\nx = 1\n"
        violations = list(check_banner_comment(_DOC_PATH, source))
        assert [(v.rule, v.line) for v in violations] == [
            (RS_BANNER_COMMENT, 1),
            (RS_BANNER_COMMENT, 3),
        ]


class TestCheckDoubleSpaceAfterPeriod:
    @pytest.mark.parametrize(
        "source",
        [
            'def f():\n    """First sentence.  Second sentence."""\n',
            'def f():\n    """Summary.\n\n    First.  Second.\n    """\n',
            'def f():\n    """Summary.   Three spaces here."""\n',
            'def f():\n    """Warning!  Do not proceed."""\n',
            'def f():\n    """Is it ready?  Let us check."""\n',
        ],
        ids=[
            "single-line",
            "body-paragraph",
            "three-spaces",
            "exclamation-mark",
            "question-mark",
        ],
    )
    def test_DocstringDoubleSpace_Flags(self, source: str) -> None:
        violations = list(check_double_space_after_period(Path("src/x.py"), source))
        assert len(violations) >= 1
        assert violations[0].rule == RS_DOUBLE_SPACE_AFTER_PERIOD

    def test_CommentDoubleSpace_Flags(self) -> None:
        source = "# First sentence.  Second sentence.\n"
        violations = list(check_double_space_after_period(Path("src/x.py"), source))
        assert len(violations) == 1
        assert violations[0].rule == RS_DOUBLE_SPACE_AFTER_PERIOD

    @pytest.mark.parametrize(
        ("path", "source"),
        [
            (Path("config.yaml"), "# First.  Second.\n"),
            (Path("config.toml"), "# First.  Second.\n"),
            (Path("script.sh"), "# First.  Second.\n"),
        ],
        ids=["yaml", "toml", "shell"],
    )
    def test_CrossLanguageComment_Flags(self, path: Path, source: str) -> None:
        violations = list(check_double_space_after_period(path, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_DOUBLE_SPACE_AFTER_PERIOD

    @pytest.mark.parametrize(
        "source",
        [
            'def f():\n    """First sentence. Second sentence."""\n',
            "# Single space after period. Like this.\n",
            'x = "hello.  world"\n',
        ],
        ids=["single-space-docstring", "single-space-comment", "string-literal"],
    )
    def test_ConformingProse_NoViolation(self, source: str) -> None:
        assert list(check_double_space_after_period(Path("src/x.py"), source)) == []

    def test_UnsupportedSuffix_NoViolation(self) -> None:
        source = "First.  Second.\n"
        assert list(check_double_space_after_period(Path("data.txt"), source)) == []

    def test_MultipleOccurrences_FlagsEach(self) -> None:
        source = 'def f():\n    """One.  Two.  Three."""\n'
        violations = list(check_double_space_after_period(Path("src/x.py"), source))
        assert len(violations) == 2
