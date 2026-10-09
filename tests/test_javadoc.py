from pathlib import Path

import pytest

from repostyle.rules import (
    RS_ACRONYM_CASING_IN_PROSE,
    RS_DISFAVORED_GCP_TERM,
    RS_DOUBLE_SPACE_AFTER_PERIOD,
    RS_FILLER_DOCSTRING_OPENING,
    RS_IMPERATIVE_DOCSTRING_OPENING,
    RS_TEMPORAL_MARKER,
    RS_TERMINAL_PUNCTUATION,
    check_acronym_casing_in_docstrings,
    check_disfavored_gcp_term_in_docstrings,
    check_docstring_temporal_markers,
    check_docstring_terminal_punctuation,
    check_double_space_after_period,
    check_filler_docstring_opening,
    check_imperative_docstring_opening,
    check_nonstandard_dash_in_docstrings,
)
from repostyle.rules._doc_blocks import internal_doc_blocks
from repostyle.runner import fix_path

_PATH = Path("src/main/java/io/example/Widget.java")

_DOCUMENTED_METHOD = """\
class Widget {
  /**
   * Returns the count of {@code items} held, or zero when empty.
   *
   * <p>The count is read under the lock.
   *
   * <ul>
   *   <li>one item
   *   <li>another item
   * </ul>
   *
   * <pre>{@code
   * int n = widget.count();
   * }</pre>
   *
   * @param items the items to count
   * @return the count
   */
  int count(List<Item> items) {
    return items.size();
  }
}
"""


class TestJavadocSegmentation:
    def test_DocumentedMethod_SplitsIntoSummaryBodyBulletsAndTags(self) -> None:
        (block,) = internal_doc_blocks(_PATH, _DOCUMENTED_METHOD)
        assert [(unit.kind, unit.text) for unit in block.units] == [
            ("summary", "Returns the count of `items` held, or zero when empty."),
            ("body", "The count is read under the lock."),
            ("bullet", "one item"),
            ("bullet", "another item"),
            ("tag", "@param items the items to count"),
            ("tag", "@return the count"),
        ]

    def test_DocumentedMethod_AnchorsOnTheOpeningDelimiter(self) -> None:
        (block,) = internal_doc_blocks(_PATH, _DOCUMENTED_METHOD)
        assert (block.lineno, block.col) == (2, 3)

    def test_ScanLines_BlankGutterCodeTagsAndCaptions(self) -> None:
        (block,) = internal_doc_blocks(_PATH, _DOCUMENTED_METHOD)
        lines = dict(block.scan_lines)
        assert (
            lines[3].strip()
            == "Returns the count of               held, or zero when empty."
        )
        assert lines[16].strip() == "the items to count"

    def test_InlineTagWrappedAcrossLines_IsBlankedWhole(self) -> None:
        source = _javadoc(
            "Refused under the name {@code", "GCP_URL} rather than", "another."
        )
        assert list(check_disfavored_gcp_term_in_docstrings(_PATH, source)) == []
        assert list(check_acronym_casing_in_docstrings(_PATH, source)) == []


class TestJavadocProseRules:
    def test_ImperativeSummary_IsFlaggedOnTheOpeningDelimiter(self) -> None:
        violations = list(
            check_imperative_docstring_opening(_PATH, _javadoc("Return the count."))
        )
        assert [(v.rule, v.line, v.col) for v in violations] == [
            (RS_IMPERATIVE_DOCSTRING_OPENING, 2, 3)
        ]

    def test_DescriptiveSummary_IsAccepted(self) -> None:
        source = _javadoc("Returns the count.")
        assert list(check_imperative_docstring_opening(_PATH, source)) == []

    def test_FillerSummary_IsFlagged(self) -> None:
        source = _javadoc("This method returns the count.")
        violations = list(check_filler_docstring_opening(_PATH, source))
        assert [v.rule for v in violations] == [RS_FILLER_DOCSTRING_OPENING]

    def test_EditHistoryInBody_IsFlagged(self) -> None:
        source = _javadoc("Returns the count.", "", "<p>Previously this cached it.")
        violations = list(check_docstring_temporal_markers(_PATH, source))
        assert [v.rule for v in violations] == [RS_TEMPORAL_MARKER]

    def test_UnpunctuatedSummary_IsFlagged(self) -> None:
        source = _javadoc("Returns the count")
        violations = list(check_docstring_terminal_punctuation(_PATH, source))
        assert [v.rule for v in violations] == [RS_TERMINAL_PUNCTUATION]

    def test_UnpunctuatedBlockTag_IsAccepted(self) -> None:
        source = _javadoc("Returns the count.", "", "@return the count")
        assert list(check_docstring_terminal_punctuation(_PATH, source)) == []

    @pytest.mark.parametrize(
        ("prose", "rule"),
        [
            ("Reads the object from GCS.", RS_DISFAVORED_GCP_TERM),
            ("Resolves the url to fetch.", RS_ACRONYM_CASING_IN_PROSE),
        ],
        ids=["gcp_term", "acronym"],
    )
    def test_MiswrittenTermInProse_IsFlagged(self, prose: str, rule: str) -> None:
        source = _javadoc(prose)
        violations = [
            *check_disfavored_gcp_term_in_docstrings(_PATH, source),
            *check_acronym_casing_in_docstrings(_PATH, source),
        ]
        assert [v.rule for v in violations] == [rule]

    def test_TermInsideCodeTag_IsAccepted(self) -> None:
        source = _javadoc("Reads {@code gcs_url} via {@link GcsClient}.")
        assert list(check_disfavored_gcp_term_in_docstrings(_PATH, source)) == []
        assert list(check_acronym_casing_in_docstrings(_PATH, source)) == []

    def test_EmDash_IsLeftForJavadocToRender(self) -> None:
        source = _javadoc("Returns the count — or zero.")
        assert list(check_nonstandard_dash_in_docstrings(_PATH, source)) == []

    @pytest.mark.parametrize(
        "prose",
        ["Returns the count. {@code x} is never negative.", "Returns the count."],
        ids=["before_code_tag", "before_closer"],
    )
    def test_SpaceBeforeBlankedMarkup_IsNotDoubled(self, prose: str) -> None:
        source = f"class Widget {{\n  /** {prose} */\n  void run() {{}}\n}}\n"
        assert list(check_double_space_after_period(_PATH, source)) == []

    def test_DoubleSpace_IsFlagged(self) -> None:
        source = _javadoc("Returns the count.  Never negative.")
        violations = list(check_double_space_after_period(_PATH, source))
        assert [v.rule for v in violations] == [RS_DOUBLE_SPACE_AFTER_PERIOD]


class TestJavadocBoundaries:
    def test_CodeAfterTheCloser_IsNotProse(self) -> None:
        source = (
            "class Widget {\n"
            '  /** Returns the flag. */ String s() { return "use gcp, ok"; }\n'
            "}\n"
        )
        assert list(check_disfavored_gcp_term_in_docstrings(_PATH, source)) == []
        assert list(check_docstring_terminal_punctuation(_PATH, source)) == []

    @pytest.mark.parametrize(
        "lines",
        [
            ("Runs the query.", "", "<p>Read <code>gcp_url</code> first."),
            ("Runs the query.", "", '<pre class="code">', "gcp_url = 1", "</pre>"),
        ],
        ids=["code_element", "pre_with_attributes"],
    )
    def test_CodeMarkup_IsNotProse(self, lines: tuple[str, ...]) -> None:
        source = _javadoc(*lines)
        assert list(check_disfavored_gcp_term_in_docstrings(_PATH, source)) == []

    def test_HeadingAndTable_AreNotParagraphs(self) -> None:
        source = _javadoc(
            "Runs the query.",
            "",
            "<h2>Thread safety</h2>",
            "",
            "<table>",
            "  <tr><td>one</td></tr>",
            "</table>",
        )
        (block,) = internal_doc_blocks(_PATH, source)
        assert [unit.kind for unit in block.units] == ["summary"]


class TestJavadocFixes:
    def test_FixPath_RepairsJavadocProseInPlace(self, tmp_path: Path) -> None:
        java = tmp_path / "Widget.java"
        java.write_text(
            _javadoc("Reads the url from GCS.  Never empty."), encoding="utf-8"
        )
        enabled = {RS_ACRONYM_CASING_IN_PROSE, RS_DISFAVORED_GCP_TERM}
        enabled |= {RS_DOUBLE_SPACE_AFTER_PERIOD}
        assert fix_path(java, enabled)
        assert java.read_text(encoding="utf-8") == _javadoc(
            "Reads the URL from Cloud Storage. Never empty."
        )


def _javadoc(*lines: str) -> str:
    body = "".join(f"   * {line}\n" if line else "   *\n" for line in lines)
    return f"class Widget {{\n  /**\n{body}   */\n  void run() {{}}\n}}\n"
