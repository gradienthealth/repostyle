from pathlib import Path

import pytest

from repostyle.languages import java_code_tokens, java_declarations
from repostyle.rules import (
    RS_ASSERTION_LIBRARY,
    RS_COGNITIVE_COMPLEXITY,
    RS_DOC_VALUE_SIGNAL,
    RS_LOWERCASE_ENTRY_DESCRIPTION,
    RS_NONSTANDARD_DASH,
    RS_TERMINAL_PUNCTUATION,
    check_java_assertion_library,
    check_java_cognitive_complexity,
    check_java_doc_value_signal,
    check_javadoc_tag_casing,
    check_javadoc_tag_punctuation,
    check_nonstandard_dash_in_docstrings,
)
from repostyle.rules.java._complexity import java_cognitive_complexity
from repostyle.rules.prose_typography import fix_nonstandard_dash_in_docstrings
from repostyle.runner import fix_path, resolve_rules_for_paths

_PATH = Path("src/main/java/io/example/Widget.java")

_TEST_PATH = Path("src/test/java/io/example/WidgetTest.java")


class TestJavadocDash:
    @pytest.mark.parametrize(
        "prose",
        ["Returns the count -- never negative.", "Returns the count—never negative."],
        ids=["double_hyphen", "glued_em_dash"],
    )
    def test_NonstandardDash_IsFlagged(self, prose: str) -> None:
        violations = list(check_nonstandard_dash_in_docstrings(_PATH, _javadoc(prose)))
        assert [v.rule for v in violations] == [RS_NONSTANDARD_DASH]
        assert "' — '" in violations[0].message

    def test_SpacedEmDash_IsAccepted(self) -> None:
        source = _javadoc("Returns the count — never negative.")
        assert list(check_nonstandard_dash_in_docstrings(_PATH, source)) == []

    def test_DoubleHyphen_RewritesToSpacedEmDash(self) -> None:
        source = _javadoc("Returns the count -- never negative.")
        expected = _javadoc("Returns the count — never negative.")
        assert fix_nonstandard_dash_in_docstrings(_PATH, source) == expected

    def test_DashAtAWrapPoint_KeepsNoEdgeSpace(self) -> None:
        source = _javadoc("Returns the count --", "never negative.")
        expected = _javadoc("Returns the count —", "never negative.")
        assert fix_nonstandard_dash_in_docstrings(_PATH, source) == expected


class TestJavadocTagPunctuation:
    def test_PhraseWithPeriod_IsFlagged(self) -> None:
        source = _javadoc("Runs.", "", "@param limit the most rows to read.")
        violations = list(check_javadoc_tag_punctuation(_PATH, source))
        assert [v.rule for v in violations] == [RS_TERMINAL_PUNCTUATION]
        assert "drop the trailing period" in violations[0].message

    def test_PhrasesWithoutPeriods_AreAccepted(self) -> None:
        source = _javadoc(
            "Runs.", "", "@param limit the most rows to read", "@return the rows read"
        )
        assert list(check_javadoc_tag_punctuation(_PATH, source)) == []

    def test_SentenceBesideAPhrase_AsksThePhraseForAPeriod(self) -> None:
        source = _javadoc(
            "Runs.",
            "",
            "@param limit the most rows to read. Zero reads none.",
            "@return the rows read",
        )
        violations = list(check_javadoc_tag_punctuation(_PATH, source))
        assert [(v.rule, v.line) for v in violations] == [(RS_TERMINAL_PUNCTUATION, 6)]
        assert "ends with a period" in violations[0].message

    @pytest.mark.parametrize(
        ("before", "after"),
        [
            (
                "  /** @return the count. Never negative */ int count();\n",
                "  /** @return the count. Never negative. */ int count();\n",
            ),
            (
                "  /**\n   * @param mode the mode. It picks one of:\n"
                "   *     <ul><li>fast\n   *     </ul>\n   * @return the rows\n   */\n",
                "  /**\n   * @param mode the mode. It picks one of:\n"
                "   *     <ul><li>fast\n   *     </ul>\n   * @return the rows.\n   */\n",
            ),
        ],
        ids=["code_after_closer", "list_closing_tag"],
    )
    def test_MissingPeriod_LandsAfterTheProse(
        self, before: str, after: str, tmp_path: Path
    ) -> None:
        java = tmp_path / "Widget.java"
        java.write_text(f"class Widget {{\n{before}}}\n", encoding="utf-8")
        fix_path(java, {RS_TERMINAL_PUNCTUATION})
        assert java.read_text(encoding="utf-8") == f"class Widget {{\n{after}}}\n"

    def test_FixPath_DropsAPhrasePeriod(self, tmp_path: Path) -> None:
        java = tmp_path / "Widget.java"
        java.write_text(
            _javadoc("Runs.", "", "@param limit the most rows to read."),
            encoding="utf-8",
        )
        assert fix_path(java, {RS_TERMINAL_PUNCTUATION})
        assert java.read_text(encoding="utf-8") == _javadoc(
            "Runs.", "", "@param limit the most rows to read"
        )


class TestJavadocTagCasing:
    def test_CapitalizedArticle_IsFlagged(self) -> None:
        source = _javadoc("Runs.", "", "@return The rows read")
        violations = list(check_javadoc_tag_casing(_PATH, source))
        assert [v.rule for v in violations] == [RS_LOWERCASE_ENTRY_DESCRIPTION]

    @pytest.mark.parametrize(
        "tag",
        ["@return the rows read", "@param host DICOM host to dial", "@see Widget"],
        ids=["lowercase", "acronym", "reference_tag"],
    )
    def test_ConventionalOpening_IsAccepted(self, tag: str) -> None:
        source = _javadoc("Runs.", "", tag)
        assert list(check_javadoc_tag_casing(_PATH, source)) == []


class TestJavaAssertionLibrary:
    def test_JUnitAssertionUnderTheTruthDefault_IsFlagged(self) -> None:
        source = (
            "import static org.junit.jupiter.api.Assertions.assertEquals;\n"
            "class WidgetTest {}\n"
        )
        violations = list(check_java_assertion_library(_TEST_PATH, source))
        assert [v.rule for v in violations] == [RS_ASSERTION_LIBRARY]

    def test_TruthWithJUnitAssertThrows_IsAccepted(self) -> None:
        source = (
            "import static com.google.common.truth.Truth.assertThat;\n"
            "import static org.junit.jupiter.api.Assertions.assertThrows;\n"
            "class WidgetTest {}\n"
        )
        assert list(check_java_assertion_library(_TEST_PATH, source)) == []

    def test_QualifiedAssertionsCall_IsFlagged(self) -> None:
        source = (
            "import org.junit.jupiter.api.Assertions;\n"
            "class WidgetTest { void a_b() { Assertions.assertEquals(1, 1); } }\n"
        )
        violations = list(check_java_assertion_library(_TEST_PATH, source))
        assert [v.rule for v in violations] == [RS_ASSERTION_LIBRARY]

    def test_ConfiguredJUnit_AcceptsJUnitAndRejectsTruth(self, tmp_path: Path) -> None:
        (tmp_path / "repostyle.toml").write_text(
            'assertion-library = "junit"\n', encoding="utf-8"
        )
        test_file = tmp_path / "src" / "test" / "WidgetTest.java"
        source = (
            "import static org.junit.jupiter.api.Assertions.assertEquals;\n"
            "import static com.google.common.truth.Truth.assertThat;\n"
            "class WidgetTest {}\n"
        )
        violations = list(check_java_assertion_library(test_file, source))
        assert [v.line for v in violations] == [2]


class TestAssertionLibrarySetting:
    def test_UnknownLibrary_IsRefused(self, tmp_path: Path) -> None:
        (tmp_path / "repostyle.toml").write_text(
            'assertion-library = "assertJ"\n', encoding="utf-8"
        )
        with pytest.raises(ValueError, match="assertion-library"):
            resolve_rules_for_paths([tmp_path])


class TestJavaReviewSignals:
    def test_DeeplyBranchedMethod_IsOverTheComplexityLimit(self) -> None:
        body = (
            "if (a) { if (b) { if (c) { if (d) { if (e) { if (f) { run(); } } } } } }"
        )
        source = f"class W {{\n  void f() {{ {body} }}\n}}\n"
        violations = list(check_java_cognitive_complexity(_PATH, source))
        assert [v.rule for v in violations] == [RS_COGNITIVE_COMPLEXITY]

    @pytest.mark.parametrize(
        "body",
        [
            "try { if (a) { run(); } } finally { if (b) { run(); } }",
            "switch (m) { case A -> { if (a) { run(); } } default -> run(); }",
        ],
        ids=["try_finally", "switch_rule"],
    )
    def test_NonBranchingBlock_AddsNoNesting(self, body: str) -> None:
        code = java_code_tokens(f"class W {{ void f() {{ {body} }} }}")
        (_, method) = java_declarations(f"class W {{ void f() {{ {body} }} }}")
        expected = 2 if body.startswith("try") else 3
        assert java_cognitive_complexity(code, method.body) == expected

    def test_UndocumentedManyParameterMethod_IsSignaled(self) -> None:
        source = "class W {\n  void f(int a, int b, int c, int d) {}\n}\n"
        violations = list(check_java_doc_value_signal(_PATH, source))
        assert [v.rule for v in violations] == [RS_DOC_VALUE_SIGNAL]

    @pytest.mark.parametrize(
        "member",
        [
            "/** Adds them. */\n  void f(int a, int b, int c, int d) {}",
            "private void f(int a, int b, int c, int d) {}",
            "@Override\n  public void f(int a, int b, int c, int d) {}",
            "void f(int a) { run(); }",
        ],
        ids=["documented", "private", "override", "trivial"],
    )
    def test_ExemptOrTrivialMethod_IsQuiet(self, member: str) -> None:
        source = f"class W {{\n  {member}\n}}\n"
        assert list(check_java_doc_value_signal(_PATH, source)) == []


def _javadoc(*lines: str) -> str:
    body = "".join(f"   * {line}\n" if line else "   *\n" for line in lines)
    return f"class Widget {{\n  /**\n{body}   */\n  void run() {{}}\n}}\n"
