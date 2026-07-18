from pathlib import Path

import pytest

from repostyle._comments import extract_comments
from repostyle.rules import RS_TEMPORAL_MARKER, check_comment_temporal_markers


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
        [Path("c.toml"), Path("c.yaml"), Path("c.yml")],
        ids=["toml", "yaml", "yml"],
    )
    def test_MarkerInComment_FlagsAcrossLanguages(self, path: Path) -> None:
        source = "# we decided to hardcode this\n"
        violations = list(check_comment_temporal_markers(path, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_TEMPORAL_MARKER


def _comments(path: Path, source: str) -> list[tuple[int, int, bool, str]]:
    """Collects comments as `(line, column, is_trailing, stripped text)`."""
    return [
        (c.lineno, c.column, c.is_trailing, c.string.lstrip("#").strip())
        for c in extract_comments(path, source)
    ]
