from pathlib import Path

import pytest

from repostyle._comments import extract_comments
from repostyle.rules import (
    RS_BANNER_COMMENT,
    RS_BULLET_ITEM_CASING,
    RS_COMMENT_TAG_FORMAT,
    RS_DOC_FILL,
    RS_NONSTANDARD_DASH,
    RS_TEMPORAL_MARKER,
    RS_TERMINAL_PUNCTUATION,
    check_banner_comment,
    check_bullet_item_casing_in_comments,
    check_comment_tag_format,
    check_comment_temporal_markers,
    check_comment_terminal_punctuation,
    check_doc_fill,
    check_nonstandard_dash_in_comments,
)


class TestExtractComments:
    def test_PythonSource_YieldsOwnLineAndTrailingComments(self) -> None:
        source = "# lead\nx = 1  # trail\ns = '# not a comment'\n"
        assert _comments(Path("m.py"), source) == [
            (1, 0, False, "lead"),
            (2, 7, True, "trail"),
        ]

    def test_TomlSource_YieldsOwnLineAndTrailingComments(self) -> None:
        source = "# lead\nkey = 1  # trail\n"
        assert _comments(Path("c.toml"), source) == [
            (1, 0, False, "lead"),
            (2, 9, True, "trail"),
        ]

    def test_YamlSource_YieldsOwnLineAndTrailingComments(self) -> None:
        source = "# lead\nkey: 1  # trail\n"
        assert _comments(Path("c.yaml"), source) == [
            (1, 0, False, "lead"),
            (2, 8, True, "trail"),
        ]

    @pytest.mark.parametrize(
        "source",
        [
            'key = "a # b"\n',
            "key = 'a # b'\n",
            '"""\na # b\n"""\n',
            'key = "a \\" # b"\n',
        ],
        ids=["basic_string", "literal_string", "multiline_string", "escaped_quote"],
    )
    def test_HashInsideTomlString_NotAComment(self, source: str) -> None:
        assert _comments(Path("c.toml"), source) == []

    def test_CommentAfterTomlMultilineString_IsFound(self) -> None:
        source = 'a = """\nx # inside\n"""  # outside\n'
        assert _comments(Path("c.toml"), source) == [(3, 5, True, "outside")]

    @pytest.mark.parametrize(
        "source",
        [
            'key: "a # b"\n',
            "key: 'a # b'\n",
            "url: http://example.com#frag\n",
            "key: 'it''s # ok'\n",
        ],
        ids=[
            "double_quoted",
            "single_quoted",
            "no_space_before_hash",
            "single_quote_doubled",
        ],
    )
    def test_HashNotOpeningYamlComment_IsIgnored(self, source: str) -> None:
        assert _comments(Path("c.yaml"), source) == []

    def test_YamlBlockScalarContent_IsNotScanned(self) -> None:
        source = "block: |\n  literal # not a comment\n  more\nnext: 1  # real\n"
        assert _comments(Path("c.yaml"), source) == [(4, 9, True, "real")]

    def test_CommentOnYamlBlockIntroducer_IsFound(self) -> None:
        source = "block: >  # note\n  folded # literal\ndone: 1\n"
        assert _comments(Path("c.yaml"), source) == [(1, 10, True, "note")]

    def test_ShellSource_YieldsOwnLineAndTrailingComments(self) -> None:
        source = "# lead\nx=1  # trail\n"
        assert _comments(Path("s.sh"), source) == [
            (1, 0, False, "lead"),
            (2, 5, True, "trail"),
        ]

    @pytest.mark.parametrize(
        "source",
        [
            'echo "a # b"\n',
            "echo 'a # b'\n",
            "echo ${v#pat}\n",
            "echo ${v##pat}\n",
            "echo $# args\n",
            "echo a#b\n",
            "x=$'a # b'\n",
            "x=$((16#ff))\n",
            "x=$((1 << 2))\n",
            "echo \\# literal\n",
        ],
        ids=[
            "double_quoted",
            "single_quoted",
            "parameter_expansion",
            "parameter_expansion_greedy",
            "positional_count",
            "glued_word",
            "ansi_c_string",
            "arithmetic_base",
            "arithmetic_shift",
            "escaped_hash",
        ],
    )
    def test_HashNotOpeningShellComment_IsIgnored(self, source: str) -> None:
        assert _comments(Path("s.sh"), source) == []

    def test_ShellHeredocBody_IsNotScanned(self) -> None:
        source = "cat <<EOF\n  literal # not a comment\nEOF\nnext=1  # real\n"
        assert _comments(Path("s.sh"), source) == [(4, 8, True, "real")]

    def test_ShellDashHeredoc_TerminatesOnTabIndentedDelimiter(self) -> None:
        source = "cat <<-END\n\tbody # not\n\tEND\nx=1  # real\n"
        assert _comments(Path("s.sh"), source) == [(4, 5, True, "real")]

    def test_CommentOnShellHeredocRedirection_IsFound(self) -> None:
        source = "cat <<'EOF'  # note\nfolded # literal\nEOF\n"
        assert _comments(Path("s.sh"), source) == [(1, 13, True, "note")]

    def test_ShellHereString_IsNotTreatedAsHeredoc(self) -> None:
        source = 'grep foo <<< "$input"  # note\nx=1  # real\n'
        assert _comments(Path("s.sh"), source) == [
            (1, 23, True, "note"),
            (2, 5, True, "real"),
        ]

    def test_ShellDoubleQuotedStringSpanningLines_IsNotScanned(self) -> None:
        source = 'x="line1\nline2 # not"\nz=1  # real\n'
        assert _comments(Path("s.sh"), source) == [(3, 5, True, "real")]

    def test_ShellShebang_IsYieldedAsAComment(self) -> None:
        source = "#!/usr/bin/env bash\nx=1  # real\n"
        assert _comments(Path("s.sh"), source) == [
            (1, 0, False, "!/usr/bin/env bash"),
            (2, 5, True, "real"),
        ]

    def test_UnsupportedSuffix_YieldsNothing(self) -> None:
        assert _comments(Path("notes.txt"), "# a comment\n") == []

    @pytest.mark.parametrize(
        "source",
        [
            "# lead\nif x:\n\tpass\n        pass\n",
            '# lead\nx = "unterminated\n',
        ],
        ids=["indentation_error", "unterminated_string"],
    )
    def test_UnparseablePython_DoesNotRaise(self, source: str) -> None:
        # tokenizing stops at the error, so comments before it still survive
        assert _comments(Path("m.py"), source) == [(1, 0, False, "lead")]


class TestTemporalMarkerCrossLanguage:
    @pytest.mark.parametrize(
        "path",
        [Path("c.toml"), Path("c.yaml"), Path("c.yml"), Path("s.sh")],
        ids=["toml", "yaml", "yml", "shell"],
    )
    def test_MarkerInComment_FlagsAcrossLanguages(self, path: Path) -> None:
        source = "# we decided to hardcode this\n"
        violations = list(check_comment_temporal_markers(path, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_TEMPORAL_MARKER


class TestNonstandardDashCrossLanguage:
    @pytest.mark.parametrize(
        "path",
        [Path("c.toml"), Path("c.yaml"), Path("c.yml"), Path("s.sh")],
        ids=["toml", "yaml", "yml", "shell"],
    )
    def test_EmDashInComment_FlagsAcrossLanguages(self, path: Path) -> None:
        source = "# tuned — carefully\n"
        violations = list(check_nonstandard_dash_in_comments(path, source))
        assert [v.rule for v in violations] == [RS_NONSTANDARD_DASH]


class TestBannerCommentCrossLanguage:
    @pytest.mark.parametrize(
        "path",
        [Path("c.toml"), Path("c.yaml"), Path("s.sh")],
        ids=["toml", "yaml", "shell"],
    )
    def test_DividerComment_FlagsAcrossLanguages(self, path: Path) -> None:
        violations = list(check_banner_comment(path, "# =====\n"))
        assert [v.rule for v in violations] == [RS_BANNER_COMMENT]

    def test_YamlCommentedDocumentSeparator_NotFlagged(self) -> None:
        source = "# ---\nkey: value\n"
        assert list(check_banner_comment(Path("c.yaml"), source)) == []

    def test_ShellShebang_NotFlagged(self) -> None:
        source = "#!/usr/bin/env bash\necho hi\n"
        assert list(check_banner_comment(Path("s.sh"), source)) == []


class TestBulletItemCasingCrossLanguage:
    def test_YamlCommentList_FlagsLowercaseItem(self) -> None:
        source = "# - the thing. Does a foo.\n# - The other thing.\nkey: value\n"
        violations = list(check_bullet_item_casing_in_comments(Path("c.yaml"), source))
        assert [v.rule for v in violations] == [RS_BULLET_ITEM_CASING]


class TestShellCommentRules:
    def test_MalformedTag_FlagsTagFormat(self) -> None:
        violations = list(check_comment_tag_format(Path("s.sh"), "# todo: fix it\n"))
        assert [v.rule for v in violations] == [RS_COMMENT_TAG_FORMAT]

    def test_ProseComment_FlagsTerminalPunctuation(self) -> None:
        source = "x=1  # First sentence. Second one with no period\n"
        violations = list(check_comment_terminal_punctuation(Path("s.sh"), source))
        assert [v.rule for v in violations] == [RS_TERMINAL_PUNCTUATION]

    def test_UnderWrappedBlock_FlagsDocFill(self) -> None:
        source = "# a short first line\n# and a second line that could have joined the first\n"
        violations = list(check_doc_fill(Path("s.sh"), source))
        assert any(v.rule == RS_DOC_FILL for v in violations)

    def test_LineContinuationBlock_SkipsDocFill(self) -> None:
        source = (
            "#   sudo systemd-run --pipe --wait --collect --same-dir \\\n"
            "#        --setenv=ENVIRONMENT=merlin \\\n"
            "#        ./bootstrap.sh\n"
        )
        assert list(check_doc_fill(Path("s.sh"), source)) == []

    def test_Shebang_IsSkippedByProseRules(self) -> None:
        source = "#!/usr/bin/env bash\n"
        assert list(check_comment_terminal_punctuation(Path("s.sh"), source)) == []
        assert list(check_comment_tag_format(Path("s.sh"), source)) == []


def _comments(path: Path, source: str) -> list[tuple[int, int, bool, str]]:
    """Collects comments as `(line, column, is_trailing, stripped text)`."""
    return [
        (c.lineno, c.column, c.is_trailing, c.string.lstrip("#").strip())
        for c in extract_comments(path, source)
    ]
