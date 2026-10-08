from pathlib import Path

import pytest

from repostyle.languages import java_declarations
from repostyle.rules import (
    RS_ACRONYM_CASING,
    RS_ARG_DESCRIBED_IN_PROSE,
    RS_BANNED_ABBREVIATION,
    RS_DISCOURAGED_CLASS_SUFFIX,
    RS_DURATION_AS_TIMEDELTA,
    RS_RECORD_COMPONENT_UNDOCUMENTED,
    RS_TOO_MANY_POSITIONAL_ARGS,
    check_java_acronym_as_word,
    check_java_banned_abbreviation,
    check_java_discouraged_class_suffix,
    check_java_duration_constant,
    check_java_param_described_in_prose,
    check_java_too_many_parameters,
    check_record_component_tags,
)
from repostyle.rules._registry import run_rule

_PATH = Path("src/main/java/io/example/Widget.java")

_SERVICE = """\
package io.example;

import java.util.Map;

/** Serves widgets. */
@Singleton
public final class WidgetService implements Service {
  private static final int LIMIT = 3;
  private final Map<String, Integer> counts = new HashMap<>(Map.of("a", 1));

  static {
    register();
  }

  public WidgetService(@Named("x") final Store store, int limit) {
    this.store = store;
  }

  /** Returns the count. */
  @Override
  public <T extends Widget> List<T> find(String key, Class<T> type) throws IOException {
    Runnable r = () -> { int local = 1; };
    return List.of();
  }

  enum Mode {
    ON("on"),
    OFF("off");

    private final String label;
  }

  record Pair(String left, @Nullable String right) {
    Pair {
      Objects.requireNonNull(left);
    }
  }

  interface Listener {
    void onEvent(Event event);
  }
}
"""


class TestJavaDeclarations:
    def test_ServiceSource_YieldsEachTypeAndMember(self) -> None:
        summary = [(d.kind, d.owner, d.name) for d in java_declarations(_SERVICE)]
        assert summary == [
            ("class", "", "WidgetService"),
            ("field", "WidgetService", "LIMIT"),
            ("field", "WidgetService", "counts"),
            ("constructor", "WidgetService", "WidgetService"),
            ("method", "WidgetService", "find"),
            ("enum", "WidgetService", "Mode"),
            ("field", "Mode", "label"),
            ("record", "WidgetService", "Pair"),
            ("interface", "WidgetService", "Listener"),
            ("method", "Listener", "onEvent"),
        ]

    def test_Method_CarriesItsHeader(self) -> None:
        find = next(d for d in java_declarations(_SERVICE) if d.name == "find")
        assert find.modifiers == {"public"}
        assert find.annotations == ("Override",)
        assert find.type_text == "List<T>"
        assert [(p.type_text, p.name) for p in find.parameters] == [
            ("String", "key"),
            ("Class<T>", "type"),
        ]
        assert find.doc is not None
        assert find.body is not None

    def test_AnnotatedFinalParameter_KeepsTypeAndName(self) -> None:
        constructor = next(
            d for d in java_declarations(_SERVICE) if d.kind == "constructor"
        )
        assert [(p.type_text, p.name) for p in constructor.parameters] == [
            ("Store", "store"),
            ("int", "limit"),
        ]

    def test_GenericField_TypeKeepsItsCommaArgument(self) -> None:
        counts = next(d for d in java_declarations(_SERVICE) if d.name == "counts")
        assert counts.type_text == "Map<String,Integer>"

    def test_NonSealedClass_KeepsItsMembers(self) -> None:
        source = (
            "public non-sealed class Top {\n"
            "  static non-sealed class Inner implements Shape {\n"
            "    void parse() {}\n"
            "  }\n"
            "}\n"
        )
        summary = [(d.kind, d.name, d.modifiers) for d in java_declarations(source)]
        assert summary == [
            ("class", "Top", {"public", "non-sealed"}),
            ("class", "Inner", {"static", "non-sealed"}),
            ("method", "parse", frozenset()),
        ]

    def test_Record_ListsItsComponents(self) -> None:
        pair = next(d for d in java_declarations(_SERVICE) if d.name == "Pair")
        assert [p.name for p in pair.parameters] == ["left", "right"]


class TestJavaAcronymAsWord:
    @pytest.mark.parametrize(
        "source",
        [
            "class DICOMScp {}",
            "class Widget { void midAssociationIOException_attaches() {} }",
            "class Widget { String remoteAE; }",
            "class Widget { void hash(String sha256HEX) {} }",
        ],
        ids=["leading_run", "run_before_word", "trailing_run", "parameter"],
    )
    def test_CapitalizedAcronym_IsFlagged(self, source: str) -> None:
        assert _rules(check_java_acronym_as_word(_PATH, source)) == [RS_ACRONYM_CASING]

    @pytest.mark.parametrize(
        "source",
        [
            "class DicomScp {}",
            "class Widget { static final int MAX_AE_LENGTH = 16; }",
            "class Widget { int getAValue() { return 1; } }",
            "class Widget { @Override public String toURI() { return x; } }",
            "class StoreIT {}",
        ],
        ids=["camel_acronym", "constant", "one_letter_word", "override", "it_suffix"],
    )
    def test_ConventionalName_IsAccepted(self, source: str) -> None:
        assert list(check_java_acronym_as_word(_PATH, source)) == []

    def test_Finding_NamesTheWordForm(self) -> None:
        (violation,) = check_java_acronym_as_word(_PATH, "class DICOMScp {}")
        assert "'Dicom'" in violation.message


class TestJavaNamingVocabulary:
    def test_AbbreviatedParameter_IsFlagged(self) -> None:
        source = "class Widget { void send(Request req) {} }"
        assert _rules(check_java_banned_abbreviation(_PATH, source)) == [
            RS_BANNED_ABBREVIATION
        ]

    def test_ManagerType_IsFlagged(self) -> None:
        source = "interface ConnectionManager {}"
        assert _rules(check_java_discouraged_class_suffix(_PATH, source)) == [
            RS_DISCOURAGED_CLASS_SUFFIX
        ]


class TestJavaContracts:
    @pytest.mark.parametrize(
        ("declaration", "factory"),
        [
            ("private static final int TIMEOUT_SECONDS = 30;", "Duration.ofSeconds"),
            ("static final long CLOSE_DELAY_MS = 50L;", "Duration.ofMillis"),
        ],
        ids=["seconds", "millis"],
    )
    def test_NumericDurationConstant_IsFlagged(
        self, declaration: str, factory: str
    ) -> None:
        (violation,) = check_java_duration_constant(
            _PATH, f"class Widget {{ {declaration} }}"
        )
        assert violation.rule == RS_DURATION_AS_TIMEDELTA
        assert factory in violation.message

    @pytest.mark.parametrize(
        "declaration",
        [
            "static final int MILLIS_PER_SECOND = 1000;",
            "static final Duration TIMEOUT_SECONDS = Duration.ofSeconds(30);",
            "private int timeoutSeconds;",
        ],
        ids=["conversion_factor", "already_duration", "instance_field"],
    )
    def test_NonDurationConstant_IsAccepted(self, declaration: str) -> None:
        source = f"class Widget {{ {declaration} }}"
        assert list(check_java_duration_constant(_PATH, source)) == []

    def test_SixParameterMethod_IsFlagged(self) -> None:
        source = "class W { void f(int a, int b, int c, int d, int e, int f) {} }"
        assert _rules(check_java_too_many_parameters(_PATH, source)) == [
            RS_TOO_MANY_POSITIONAL_ARGS
        ]

    def test_SixParameterOverride_IsAccepted(self) -> None:
        source = (
            "class W { @Override void f(int a, int b, int c, int d, int e, int f) {} }"
        )
        assert list(check_java_too_many_parameters(_PATH, source)) == []

    def test_ParameterLeadingTheSummary_IsFlagged(self) -> None:
        source = (
            "class W {\n"
            "  /** {@code sink} is invoked on the reader thread. */\n"
            "  static void execute(Request request, Consumer<Row> sink) {}\n"
            "}\n"
        )
        assert _rules(check_java_param_described_in_prose(_PATH, source)) == [
            RS_ARG_DESCRIBED_IN_PROSE
        ]

    def test_ParameterWithItsOwnTag_IsAccepted(self) -> None:
        source = (
            "class W {\n"
            "  /**\n"
            "   * Runs the request.\n"
            "   *\n"
            "   * <p>{@code sink} is invoked on the reader thread.\n"
            "   *\n"
            "   * @param sink receives each row\n"
            "   */\n"
            "  static void execute(Consumer<Row> sink) {}\n"
            "}\n"
        )
        assert list(check_java_param_described_in_prose(_PATH, source)) == []

    def test_DocumentedRecordMissingATag_FlagsTheComponent(self) -> None:
        source = (
            "/**\n"
            " * A span.\n"
            " *\n"
            " * @param start the first line\n"
            " */\n"
            "record Span(int start, int end) {}\n"
        )
        violations = list(check_record_component_tags(_PATH, source))
        assert [(v.rule, v.line, v.col) for v in violations] == [
            (RS_RECORD_COMPONENT_UNDOCUMENTED, 6, 28)
        ]

    def test_UndocumentedRecord_IsLeftToOtherRules(self) -> None:
        source = "record Span(int start, int end) {}\n"
        assert list(check_record_component_tags(_PATH, source)) == []


class TestJavaRuleDispatch:
    def test_JavaCheck_RunsOnJavaFiles(self) -> None:
        violations = list(run_rule(RS_ACRONYM_CASING, _PATH, "class DICOMScp {}"))
        assert _rules(violations) == [RS_ACRONYM_CASING]

    def test_JavaSourceInAPythonFile_NeverReachesAJavaCheck(self) -> None:
        source = "class DICOMScp {}"
        assert list(run_rule(RS_ACRONYM_CASING, Path("scp.py"), source)) == []


def _rules(violations: object) -> list[str]:
    return [violation.rule for violation in violations]
