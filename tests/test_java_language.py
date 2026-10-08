from pathlib import Path

import pytest

from repostyle.languages import JAVA, block_spans, extract_comments, lex_java
from repostyle.rules import (
    RS_ACRONYM_CASING,
    RS_COMMENT_TAG_FORMAT,
    RS_DOC_FILL,
    RS_NONSTANDARD_DASH,
    Violation,
    check_comment_tag_format,
    check_doc_fill,
    check_filename_casing,
    check_nonstandard_dash_in_comments,
)
from repostyle.rules.doc_fill import fix_doc_fill
from repostyle.runner import expand_paths, resolve_rules_for_paths
from repostyle.suppressions import filter_suppressed

_PATH = Path("src/main/java/io/example/Widget.java")

_CLASS_WITH_METHODS = """\
package io.example;

/** A widget. */
public final class Widget {
  private int count;

  // style: ignore-block[RS001]
  @Override
  public String toString() {
    return "x";
  }

  void reset() {
    count = 0;
  }
}
"""


class TestJavaComments:
    def test_LineComments_YieldOwnLineAndTrailing(self) -> None:
        source = "// lead\nint x = 1; // trail\n"
        assert _comments(source) == [
            (1, 0, False, "// lead"),
            (2, 11, True, "// trail"),
        ]

    @pytest.mark.parametrize(
        "source",
        [
            'String s = "a // b";\n',
            'String s = "a \\" // b";\n',
            'String s = """\n  a // b\n  """;\n',
            "char c = '/'; char d = '/';\n",
            "/* a // b */\n",
            "/**\n * a // b\n */\n",
        ],
        ids=[
            "string",
            "escaped_quote",
            "text_block",
            "char_literals",
            "block_comment",
            "javadoc",
        ],
    )
    def test_SlashesInsideLiteralOrBlockComment_NotAComment(self, source: str) -> None:
        assert _comments(source) == []

    def test_UnterminatedBlockComment_KeepsCommentsBeforeIt(self) -> None:
        source = "// kept\nint x; /* open\n// swallowed\n"
        assert _comments(source) == [(1, 0, False, "// kept")]

    @pytest.mark.parametrize(
        ("source", "texts"),
        [
            ("non-sealed class A", ["non-sealed", "class", "A"]),
            ("x = 1.0e-5;", ["x", "=", "1.0e-5", ";"]),
        ],
        ids=["non_sealed_modifier", "signed_exponent"],
    )
    def test_CompoundToken_LexesWhole(self, source: str, texts: list[str]) -> None:
        assert [token.text for token in lex_java(source)] == texts

    def test_Javadoc_LexesAsADocComment(self) -> None:
        kinds = [token.kind for token in lex_java("/** Doc. */\n/**/ int x;\n")]
        assert kinds == ["doc_comment", "block_comment", "ident", "ident", "op"]


class TestJavaBlockSpans:
    def test_Declarations_SpanFromJavadocOrFirstTokenToClosingBrace(self) -> None:
        assert block_spans(_PATH, _CLASS_WITH_METHODS) == (
            (1, 1),
            (3, 16),
            (5, 5),
            (8, 11),
            (10, 10),
            (13, 15),
            (14, 14),
        )

    def test_TryStatement_RunsThroughItsCatchAndFinally(self) -> None:
        source = "try {\n  a();\n} catch (E e) {\n  b();\n} finally {\n  c();\n}\n"
        assert (1, 7) in block_spans(_PATH, source)

    def test_BlockDirective_CoversTheAnnotatedMethodOnly(self) -> None:
        findings = [
            Violation(line, 1, RS_ACRONYM_CASING, "acronym") for line in (9, 10, 13)
        ]
        result = filter_suppressed(_PATH, findings, _CLASS_WITH_METHODS)
        assert [violation.line for violation in result] == [13]


class TestJavaLayout:
    @pytest.mark.parametrize(
        "path",
        [
            "src/test/java/io/example/Helpers.java",
            "module/WidgetTest.java",
            "module/WidgetIT.java",
        ],
        ids=["maven_test_tree", "test_suffix", "it_suffix"],
    )
    def test_TestTreeOrSuffix_IsTestFile(self, path: str) -> None:
        assert JAVA.is_test_file(Path(path))

    @pytest.mark.parametrize(
        "path",
        [
            "src/main/java/io/example/Widget.java",
            "src/main/java/io/example/Testing.java",
        ],
        ids=["main_tree", "test_prefix"],
    )
    def test_MainTreeClass_IsNotTestFile(self, path: str) -> None:
        assert not JAVA.is_test_file(Path(path))

    def test_ClassNamedFile_IsExemptFromFilenameCasing(self) -> None:
        assert list(check_filename_casing(_PATH, "")) == []


class TestJavaOptIn:
    def test_JavaUnlisted_IsNotWalked(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.repostyle]\n", encoding="utf-8")
        (tmp_path / "Widget.java").write_text("class Widget {}\n", encoding="utf-8")
        assert expand_paths([tmp_path]) == [tmp_path / "pyproject.toml"]

    def test_JavaListed_IsWalkedAndOtherLanguagesDropped(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[tool.repostyle]\nlanguages = ["java"]\n', encoding="utf-8"
        )
        java = tmp_path / "Widget.java"
        java.write_text("class Widget {}\n", encoding="utf-8")
        (tmp_path / "tool.py").write_text("x = 1\n", encoding="utf-8")
        assert expand_paths([tmp_path]) == [java]

    def test_ExplicitJavaFileUnlisted_IsDropped(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.repostyle]\n", encoding="utf-8")
        java = tmp_path / "Widget.java"
        java.write_text("class Widget {}\n", encoding="utf-8")
        assert expand_paths([java]) == []

    def test_UnknownLanguage_IsRefused(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[tool.repostyle]\nlanguages = ["jav"]\n', encoding="utf-8"
        )
        with pytest.raises(ValueError, match="unknown repostyle language"):
            resolve_rules_for_paths([tmp_path])

    def test_NonListLanguages_KeepsTheDefaults(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.repostyle]\n", encoding="utf-8")
        nested = tmp_path / "service"
        nested.mkdir()
        (nested / "repostyle.toml").write_text('languages = "java"\n', encoding="utf-8")
        tool = nested / "tool.py"
        tool.write_text("x = 1\n", encoding="utf-8")
        assert tool in expand_paths([tmp_path])

    def test_TargetWithoutAPom_IsWalked(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.repostyle]\n", encoding="utf-8")
        package = tmp_path / "target"
        package.mkdir()
        module = package / "aim.py"
        module.write_text("x = 1\n", encoding="utf-8")
        assert module in expand_paths([tmp_path])

    def test_MavenTargetDirectory_IsPruned(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[tool.repostyle]\nlanguages = ["java"]\n', encoding="utf-8"
        )
        (tmp_path / "pom.xml").write_text("<project/>\n", encoding="utf-8")
        generated = tmp_path / "target" / "generated-sources"
        generated.mkdir(parents=True)
        (generated / "Stub.java").write_text("class Stub {}\n", encoding="utf-8")
        assert expand_paths([tmp_path]) == []


class TestCommentRulesOnJava:
    def test_MalformedTag_IsFlagged(self) -> None:
        violations = list(check_comment_tag_format(_PATH, "// TODO fix this\n"))
        assert [violation.rule for violation in violations] == [RS_COMMENT_TAG_FORMAT]

    def test_CanonicalTag_IsAccepted(self) -> None:
        source = "// TODO(PROC-1): fix this\n"
        assert list(check_comment_tag_format(_PATH, source)) == []

    def test_EmDash_IsFlagged(self) -> None:
        violations = list(
            check_nonstandard_dash_in_comments(_PATH, "// One clause — another.\n")
        )
        assert [violation.rule for violation in violations] == [RS_NONSTANDARD_DASH]

    def test_CommentPastNinetyColumns_FillsToOneHundred(self) -> None:
        words = " ".join(["word"] * 18)
        source = f"// {words}\n// tail.\n"
        violations = list(check_doc_fill(_PATH, source))
        assert [violation.rule for violation in violations] == [RS_DOC_FILL]
        assert "100 columns" in violations[0].message

    def test_ToolDirective_IsNeitherFilledNorMerged(self) -> None:
        source = (
            "  //noinspection unchecked\n"
            "  // The cast is safe because the map only ever holds strings.\n"
        )
        assert list(check_doc_fill(_PATH, source)) == []
        assert fix_doc_fill(_PATH, source) == source

    def test_UnderWrappedComment_RewrapsBehindTheSlashes(self) -> None:
        source = "  // One short line.\n  // Another short line.\n"
        expected = "  // One short line. Another short line.\n"
        assert fix_doc_fill(_PATH, source) == expected


def _comments(source: str) -> list[tuple[int, int, bool, str]]:
    return [
        (comment.lineno, comment.column, comment.is_trailing, comment.string)
        for comment in extract_comments(_PATH, source)
    ]
