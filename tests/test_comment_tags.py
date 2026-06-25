from pathlib import Path

import pytest

from pystyle.rules import RS_COMMENT_TAG_FORMAT, check_comment_tag_format


def _target(tmp_path: Path, source: str, table: str = "") -> Path:
    if table:
        (tmp_path / "pyproject.toml").write_text(table, encoding="utf-8")
    target = tmp_path / "m.py"
    target.write_text(source, encoding="utf-8")
    return target


class TestCheckCommentTagFormat:
    @pytest.mark.parametrize(
        "source",
        [
            "# TODO(PROC-1234): fix the thing\n",
            "# FIXME(NO-ISSUE): drop this once upstream lands\n",
            "# NOTE(ABC-7): why this branch exists\n",
            "x = 1  # trailing prose, not a tag\n",
            "# This is an ordinary sentence about the code.\n",
            "# noqa: E501\n",
            "# Note that this works for the common case.\n",
            "# Hack around the broken upstream API here.\n",
            "# Review the parser before shipping.\n",
            "# HTTP GET is idempotent here.\n",
        ],
        ids=[
            "canonical-todo",
            "canonical-no-issue",
            "canonical-note",
            "trailing-prose",
            "ordinary-prose",
            "directive-prose",
            "tag-word-opening-prose",
            "tag-word-opening-prose-alias",
            "alias-word-opening-prose",
            "all-caps-non-tag-word",
        ],
    )
    def test_CanonicalOrNonTagComment_NoViolation(
        self, tmp_path: Path, source: str
    ) -> None:
        target = _target(tmp_path, source)
        assert list(check_comment_tag_format(target, source)) == []

    @pytest.mark.parametrize(
        "source",
        [
            "# XXX(PROC-1): steer to an allowed tag\n",
            "# BUG(PROC-1): another alias\n",
            "# todo(PROC-1): wrong casing\n",
            "# TODO PROC-1234: missing parentheses\n",
            "# TODO: fix this someday\n",
            "# TODO fix this someday\n",
            "# TODO(sai): a name, not a ticket\n",
            "# TODO(PROC-1) fix the thing\n",
            "# TODO(PROC-1):no space after colon\n",
        ],
        ids=[
            "alias-tag",
            "alias-bug",
            "wrong-casing",
            "missing-parens",
            "missing-ticket-colon",
            "missing-ticket-bare",
            "name-not-ticket",
            "wrong-separator",
            "no-space-after-colon",
        ],
    )
    def test_DeviatingTagComment_FlagsViolation(
        self, tmp_path: Path, source: str
    ) -> None:
        target = _target(tmp_path, source)
        violations = list(check_comment_tag_format(target, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_COMMENT_TAG_FORMAT

    def test_TrailingDeviatingComment_NoViolation(self, tmp_path: Path) -> None:
        source = "x = 1  # todo(PROC-1): trailing comment, left to ruff\n"
        target = _target(tmp_path, source)
        assert list(check_comment_tag_format(target, source)) == []

    def test_IndentedOwnLineDeviation_PointsAtHash(self, tmp_path: Path) -> None:
        source = "    # todo: fix\n"
        target = _target(tmp_path, source)
        violations = list(check_comment_tag_format(target, source))
        assert len(violations) == 1
        assert violations[0].col == 5

    def test_AliasTag_SteersToFirstAllowedTag(self, tmp_path: Path) -> None:
        source = "# XXX: clean this up\n"
        target = _target(tmp_path, source)
        violations = list(check_comment_tag_format(target, source))
        assert len(violations) == 1
        assert "TODO" in violations[0].message
        assert "XXX" not in violations[0].message

    def test_ConfiguredTicketPattern_AcceptsRepoShape(self, tmp_path: Path) -> None:
        table = '[tool.pystyle]\ncomment-ticket-pattern = "#\\\\d+"\n'
        source = "# TODO(#42): repo uses GitHub issue numbers\n"
        target = _target(tmp_path, source, table=table)
        assert list(check_comment_tag_format(target, source)) == []

    def test_ConfiguredAllowedTags_AcceptsExtraTag(self, tmp_path: Path) -> None:
        table = (
            '[tool.pystyle]\ncomment-tags = ["TODO", "FIXME", "NOTE", "HACK", "PERF"]\n'
        )
        source = "# PERF(PROC-1): hot path, revisit\n"
        target = _target(tmp_path, source, table=table)
        assert list(check_comment_tag_format(target, source)) == []

    def test_NonPythonFile_NoViolation(self, tmp_path: Path) -> None:
        source = "# todo: fix\n"
        target = tmp_path / "notes.txt"
        target.write_text(source, encoding="utf-8")
        assert list(check_comment_tag_format(target, source)) == []

    def test_UntokenizableSource_NoCrash(self, tmp_path: Path) -> None:
        source = "x = (  # todo: unbalanced paren\n"
        target = _target(tmp_path, source)
        assert list(check_comment_tag_format(target, source)) == []
