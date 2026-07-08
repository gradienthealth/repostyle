from pathlib import Path

import pytest

from repostyle.rules import (
    RS_COMMENT_TAG_FORMAT,
    RS_TAG_COMMENT_CONTINUATION_INDENT,
    check_comment_tag_format,
    check_tag_comment_continuation_indent,
)


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
        table = '[tool.repostyle]\ncomment-ticket-pattern = "#\\\\d+"\n'
        source = "# TODO(#42): repo uses GitHub issue numbers\n"
        target = _target(tmp_path, source, table=table)
        assert list(check_comment_tag_format(target, source)) == []

    def test_ConfiguredAllowedTags_AcceptsExtraTag(self, tmp_path: Path) -> None:
        table = (
            "[tool.repostyle]\n"
            'comment-tags = ["TODO", "FIXME", "NOTE", "HACK", "PERF"]\n'
        )
        source = "# PERF(PROC-1): hot path, revisit\n"
        target = _target(tmp_path, source, table=table)
        assert list(check_comment_tag_format(target, source)) == []

    @pytest.mark.parametrize(
        "suffix,source",
        [
            ("toml", '# TODO(PROC-1): fix the thing\nkey = "value"\n'),
            ("yaml", "# TODO(PROC-1): fix the thing\nkey: value\n"),
        ],
        ids=["toml", "yaml"],
    )
    def test_CanonicalTagInConfigFile_NoViolation(
        self, tmp_path: Path, suffix: str, source: str
    ) -> None:
        target = tmp_path / f"config.{suffix}"
        target.write_text(source, encoding="utf-8")
        assert list(check_comment_tag_format(target, source)) == []

    @pytest.mark.parametrize(
        "suffix,source",
        [
            ("toml", '# todo: fix the thing\nkey = "value"\n'),
            ("yaml", "# todo: fix the thing\nkey: value\n"),
        ],
        ids=["toml", "yaml"],
    )
    def test_DeviatingTagInConfigFile_FlagsViolation(
        self, tmp_path: Path, suffix: str, source: str
    ) -> None:
        target = tmp_path / f"config.{suffix}"
        target.write_text(source, encoding="utf-8")
        violations = list(check_comment_tag_format(target, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_COMMENT_TAG_FORMAT

    @pytest.mark.parametrize(
        "suffix,source",
        [
            ("toml", '# TODO(PROC-1): real comment\nkey = "value # todo: inside"\n'),
            ("yaml", '# TODO(PROC-1): real comment\nkey: "value # todo: inside"\n'),
        ],
        ids=["toml", "yaml"],
    )
    def test_HashInsideStringValue_NoViolation(
        self, tmp_path: Path, suffix: str, source: str
    ) -> None:
        target = tmp_path / f"config.{suffix}"
        target.write_text(source, encoding="utf-8")
        assert list(check_comment_tag_format(target, source)) == []

    def test_UnsupportedFile_NoViolation(self, tmp_path: Path) -> None:
        source = "# todo: fix\n"
        target = tmp_path / "notes.txt"
        target.write_text(source, encoding="utf-8")
        assert list(check_comment_tag_format(target, source)) == []

    def test_UntokenizableSource_NoCrash(self, tmp_path: Path) -> None:
        source = "x = (  # todo: unbalanced paren\n"
        target = _target(tmp_path, source)
        # the tokenizer error is swallowed upstream, so the file yields nothing
        assert list(check_comment_tag_format(target, source)) == []


class TestCheckTagCommentContinuationIndent:
    @pytest.mark.parametrize(
        "source",
        [
            "# TODO(PROC-1): rework retry\n#     wait for a deadline\n",
            "# TODO(PROC-1): fix the thing\n",
            "# TODO(PROC-1): first tag\n# TODO(PROC-2): next tag\n",
            "# TODO(PROC-1): do it.\n\n# A separate note.\n",
            "# This comment wraps\n# onto a flush line.\n",
            "# TODO(PROC-1): refactor.\n#\n#     A second paragraph.\n",
            "# TODO(PROC-1): do it\n#\tindented with a tab\n",
            "# TODO(PROC-1): do it\n## further-hashed line\n",
        ],
        ids=[
            "indented-continuation",
            "single-line-tag",
            "adjacent-tags-second-exempt",
            "blank-line-separated-note",
            "non-tag-block",
            "blank-hash-separator-skipped",
            "tab-indented-continuation",
            "extra-hash-continuation",
        ],
    )
    def test_WellFormedOrNonContinuation_NoViolation(
        self, tmp_path: Path, source: str
    ) -> None:
        target = _target(tmp_path, source)
        assert list(check_tag_comment_continuation_indent(target, source)) == []

    @pytest.mark.parametrize(
        "source",
        [
            "# TODO(PROC-1): rework retry\n# wait for a deadline\n",
            "# FIXME(NO-ISSUE): drop this\n# after upstream lands\n",
        ],
        ids=["flush-continuation", "flush-continuation-fixme"],
    )
    def test_FlushContinuation_FlagsViolation(
        self, tmp_path: Path, source: str
    ) -> None:
        target = _target(tmp_path, source)
        violations = list(check_tag_comment_continuation_indent(target, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_TAG_COMMENT_CONTINUATION_INDENT
        assert violations[0].line == 2

    def test_MixedContinuation_FlagsOnlyFlushLine(self, tmp_path: Path) -> None:
        source = (
            "# TODO(PROC-1): a long tag comment\n"
            "#     that indents its first wrap\n"
            "# but not the second wrap line\n"
        )
        target = _target(tmp_path, source)
        violations = list(check_tag_comment_continuation_indent(target, source))
        assert len(violations) == 1
        assert violations[0].line == 3

    @pytest.mark.parametrize(
        "suffix,source",
        [
            ("toml", '# TODO(PROC-1): fix\n# flush line\nkey = "value"\n'),
            ("yaml", "# TODO(PROC-1): fix\n# flush line\nkey: value\n"),
        ],
        ids=["toml", "yaml"],
    )
    def test_FlushContinuationInConfigFile_FlagsViolation(
        self, tmp_path: Path, suffix: str, source: str
    ) -> None:
        target = tmp_path / f"config.{suffix}"
        target.write_text(source, encoding="utf-8")
        violations = list(check_tag_comment_continuation_indent(target, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_TAG_COMMENT_CONTINUATION_INDENT

    def test_UnsupportedFile_NoViolation(self, tmp_path: Path) -> None:
        source = "# TODO(PROC-1): fix\n# flush line\n"
        target = tmp_path / "notes.txt"
        target.write_text(source, encoding="utf-8")
        assert list(check_tag_comment_continuation_indent(target, source)) == []


def _target(tmp_path: Path, source: str, table: str = "") -> Path:
    if table:
        (tmp_path / "pyproject.toml").write_text(table, encoding="utf-8")
    target = tmp_path / "m.py"
    target.write_text(source, encoding="utf-8")
    return target
