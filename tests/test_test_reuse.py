from pathlib import Path

import pytest

from repostyle import baseline
from repostyle.cli import main
from repostyle.rules import (
    RS_REPEATED_TEST_SETUP,
    RS_SHARED_TEST_HELPER,
    RS_TEST_PARAMETRIZATION_CANDIDATE,
    Severity,
    check_repeated_test_setup,
    check_shared_test_helper,
    check_test_parametrization_candidate,
    has_guidance,
    rule_doc,
    severity_of,
)
from repostyle.runner import lint_package, lint_path, resolve_enabled_rules

_PARAMETRIZATION_SOURCE = """\
from parser import parse

def test_parse_AcceptsAlpha():
    assert parse("alpha") == 1

def test_parse_AcceptsBeta():
    assert parse("beta") == 2

def test_parse_AcceptsGamma():
    assert parse("gamma") == 3
"""

_SETUP_SOURCE = """\
from records import make_record, store

def test_store_AcceptsAlpha():
    record = make_record("same")
    saved = store(record)
    assert saved.alpha

def test_store_AcceptsBeta():
    record = make_record("same")
    saved = store(record)
    assert saved.beta

def test_store_AcceptsGamma():
    record = make_record("same")
    saved = store(record)
    assert saved.gamma
"""


class TestCheckSharedTestHelper:
    def test_MatchingRenamedLocals_ReportsEveryOccurrence(self, tmp_path: Path) -> None:
        first = tmp_path / "tests" / "test_first.py"
        second = tmp_path / "tests" / "test_second.py"
        files = [
            (first, _helper_source("build_first", "value", "result")),
            (second, _helper_source("build_second", "item", "created")),
        ]

        findings = list(check_shared_test_helper(files))

        assert [(path, finding.rule, finding.line) for path, finding in findings] == [
            (first, RS_SHARED_TEST_HELPER, 3),
            (second, RS_SHARED_TEST_HELPER, 3),
        ]
        assert "matches 2 definitions" in findings[0][1].message
        assert "test_second.py:3" in findings[0][1].message
        assert "consider one shared helper" in findings[0][1].message

    def test_RequestedFileWithUnchangedPeer_ReportsRequestedOccurrence(
        self, tmp_path: Path
    ) -> None:
        _write_config(tmp_path)
        first = _write(tmp_path / "tests" / "test_first.py", _helper_source("one"))
        second = _write(tmp_path / "tests" / "test_second.py", _helper_source("two"))

        findings = lint_package([first], {RS_SHARED_TEST_HELPER}, root_paths=[tmp_path])

        assert list(findings) == [first.resolve()]
        assert findings[first.resolve()][0].line == 3
        assert str(second.relative_to(tmp_path)) in findings[first.resolve()][0].message

    @pytest.mark.parametrize(
        ("first_import", "second_import"),
        [
            ("from one import make", "from two import make"),
            ("from builtins import eval as make", "from one import make"),
        ],
        ids=["distinct_imports", "dynamic_namespace"],
    )
    def test_UncertainDependencyIdentity_ReportsNothing(
        self, tmp_path: Path, first_import: str, second_import: str
    ) -> None:
        first = tmp_path / "tests" / "test_first.py"
        second = tmp_path / "tests" / "test_second.py"
        files = [
            (first, _helper_source("one", import_line=first_import)),
            (second, _helper_source("two", import_line=second_import)),
        ]

        assert list(check_shared_test_helper(files)) == []

    def test_RelativeImportsInDifferentPackages_ReportsNothing(
        self, tmp_path: Path
    ) -> None:
        files = [
            (
                tmp_path / "tests" / "a" / "test_one.py",
                _helper_source("one", import_line="from .models import make"),
            ),
            (
                tmp_path / "tests" / "b" / "test_two.py",
                _helper_source("two", import_line="from .models import make"),
            ),
        ]

        assert list(check_shared_test_helper(files)) == []

    def test_ReboundImportAndWildcardImport_ReportNothing(self, tmp_path: Path) -> None:
        ordinary = _helper_source("one")
        rebound = _helper_source("two").replace(
            "from factory import make", "from factory import make\nmake = other"
        )
        wildcard = _helper_source("three").replace(
            "from factory import make", "from factory import *"
        )
        files = [
            (tmp_path / "tests" / "test_one.py", ordinary),
            (tmp_path / "tests" / "test_two.py", rebound),
            (tmp_path / "tests" / "test_three.py", wildcard),
        ]

        assert list(check_shared_test_helper(files)) == []

    def test_FixtureParameterNamesDiffer_ReportsNothing(self, tmp_path: Path) -> None:
        first = _fixture_source("client")
        second = _fixture_source("service")

        findings = check_shared_test_helper(
            [
                (tmp_path / "tests" / "test_one.py", first),
                (tmp_path / "tests" / "test_two.py", second),
            ]
        )

        assert list(findings) == []

    def test_DefinitionTimeDefaultsRemainFileSpecific(self, tmp_path: Path) -> None:
        first = _helper_source("one").replace(
            "def one(value):", "token = object()\n\ndef one(value=token):"
        )
        second = _helper_source("two").replace(
            "def two(value):", "token = object()\n\ndef two(value=token):"
        )

        findings = check_shared_test_helper(
            [
                (tmp_path / "tests" / "test_one.py", first),
                (tmp_path / "tests" / "test_two.py", second),
            ]
        )

        assert list(findings) == []

    def test_LongPeerPath_KeepsLineAndRemediation(self, tmp_path: Path) -> None:
        first = tmp_path / "tests" / "test_one.py"
        second = tmp_path / "tests" / ("nested_directory_" * 8) / "test_second.py"

        findings = list(
            check_shared_test_helper(
                [
                    (first, _helper_source("one")),
                    (second, _helper_source("two")),
                ]
            )
        )

        first_finding = next(finding for path, finding in findings if path == first)
        assert "test_second.py:3; consider one shared helper" in first_finding.message
        assert "…" in first_finding.message

    def test_ExcludedPeer_IsNeitherEvidenceNorFinding(self, tmp_path: Path) -> None:
        _write_config(tmp_path, exclude='["tests/generated/*.py"]')
        target = _write(tmp_path / "tests" / "test_one.py", _helper_source("one"))
        _write(
            tmp_path / "tests" / "generated" / "test_two.py",
            _helper_source("two"),
        )

        findings = lint_package(
            [target], {RS_SHARED_TEST_HELPER}, root_paths=[tmp_path]
        )

        assert findings == {}

    def test_LineSuppression_HidesOnlySuppressedOccurrence(
        self, tmp_path: Path
    ) -> None:
        _write_config(tmp_path)
        suppressed = _write(
            tmp_path / "tests" / "test_one.py",
            _helper_source("one").replace(
                "def one(value):", "def one(value):  # style: ignore[RS063]"
            ),
        )
        visible = _write(tmp_path / "tests" / "test_two.py", _helper_source("two"))

        hidden = lint_package(
            [suppressed], {RS_SHARED_TEST_HELPER}, root_paths=[tmp_path]
        )
        shown = lint_package([visible], {RS_SHARED_TEST_HELPER}, root_paths=[tmp_path])

        assert hidden == {}
        assert shown[visible.resolve()][0].rule == RS_SHARED_TEST_HELPER


class TestCheckTestParametrizationCandidate:
    def test_ScalarOnlyVariation_ReportsEveryCase(self, tmp_path: Path) -> None:
        path = tmp_path / "tests" / "test_parser.py"

        findings = list(
            check_test_parametrization_candidate(path, _PARAMETRIZATION_SOURCE)
        )

        assert [(finding.rule, finding.line) for finding in findings] == [
            (RS_TEST_PARAMETRIZATION_CANDIDATE, 3),
            (RS_TEST_PARAMETRIZATION_CANDIDATE, 6),
            (RS_TEST_PARAMETRIZATION_CANDIDATE, 9),
        ]
        assert all("matches 3 cases" in finding.message for finding in findings)

    @pytest.mark.parametrize(
        "source",
        [
            _PARAMETRIZATION_SOURCE.replace(
                "def test_parse_AcceptsAlpha():",
                '@pytest.mark.parametrize("value", ["alpha"])\n'
                "def test_parse_AcceptsAlpha(value):",
            ),
            _PARAMETRIZATION_SOURCE.replace('parse("alpha")', 'parse(f"alpha")'),
            _PARAMETRIZATION_SOURCE.replace('parse("alpha")', "eval('alpha')"),
            _PARAMETRIZATION_SOURCE.replace('parse("alpha")', "parse(True)"),
            _PARAMETRIZATION_SOURCE.replace('"alpha"', '"same"')
            .replace('"beta"', '"same"')
            .replace('"gamma"', '"same"')
            .replace("== 1", "== 0")
            .replace("== 2", "== 0")
            .replace("== 3", "== 0"),
        ],
        ids=[
            "existing_parametrization",
            "f_string",
            "dynamic_namespace",
            "bool_is_not_int",
            "no_varying_values",
        ],
    )
    def test_UnsupportedOrNonvaryingGroup_ReportsNothing(
        self, tmp_path: Path, source: str
    ) -> None:
        path = tmp_path / "tests" / "test_parser.py"

        assert list(check_test_parametrization_candidate(path, source)) == []

    def test_BlockSuppression_HidesOneCase(self, tmp_path: Path) -> None:
        _write_config(tmp_path)
        source = _PARAMETRIZATION_SOURCE.replace(
            "def test_parse_AcceptsAlpha():",
            "# style: ignore-block[RS064]\ndef test_parse_AcceptsAlpha():",
        )
        path = _write(tmp_path / "tests" / "test_parser.py", source)

        findings = lint_path(path, {RS_TEST_PARAMETRIZATION_CANDIDATE})

        assert [finding.line for finding in findings] == [7, 10]

    def test_DefinitionTimeDefaultsDoNotBecomeFixtureBindings(
        self, tmp_path: Path
    ) -> None:
        source = """\
from parser import parse

first = object()
second = object()
third = object()

def test_Parse_AcceptsAlpha(value=first):
    assert parse("same") == 1

def test_Parse_AcceptsBeta(value=second):
    assert parse("same") == 1

def test_Parse_AcceptsGamma(value=third):
    assert parse("same") == 1
"""

        findings = check_test_parametrization_candidate(
            tmp_path / "tests" / "test_parser.py", source
        )

        assert list(findings) == []

    def test_ReboundDefinitionTimeName_ReportsNothing(self, tmp_path: Path) -> None:
        source = """\
from parser import parse

token = first
def test_Parse_AcceptsAlpha(value=token):
    assert parse("alpha") == 1

token = second
def test_Parse_AcceptsBeta(value=token):
    assert parse("beta") == 2

token = third
def test_Parse_AcceptsGamma(value=token):
    assert parse("gamma") == 3
"""

        findings = check_test_parametrization_candidate(
            tmp_path / "tests" / "test_parser.py", source
        )

        assert list(findings) == []


class TestCheckRepeatedTestSetup:
    def test_ExactLeadingAssignments_ReportsEveryCase(self, tmp_path: Path) -> None:
        path = tmp_path / "tests" / "test_records.py"

        findings = list(check_repeated_test_setup(path, _SETUP_SOURCE))

        assert [(finding.rule, finding.line) for finding in findings] == [
            (RS_REPEATED_TEST_SETUP, 3),
            (RS_REPEATED_TEST_SETUP, 8),
            (RS_REPEATED_TEST_SETUP, 13),
        ]
        assert all("repeats 2 leading assignments" in item.message for item in findings)

    @pytest.mark.parametrize(
        "source",
        [
            _SETUP_SOURCE.replace('make_record("same")', 'make_record("other")', 1),
            _SETUP_SOURCE.replace('make_record("same")', "1").replace(
                "store(record)", "record", 3
            ),
            _SETUP_SOURCE.replace(
                'record = make_record("same")',
                'record = [make_record("same") for _ in range(1)]',
            ),
        ],
        ids=["different_value", "no_call", "comprehension"],
    )
    def test_InexactOrUnsupportedPrefix_ReportsNothing(
        self, tmp_path: Path, source: str
    ) -> None:
        path = tmp_path / "tests" / "test_records.py"

        assert list(check_repeated_test_setup(path, source)) == []

    def test_FileSuppression_HidesEveryOccurrence(self, tmp_path: Path) -> None:
        _write_config(tmp_path)
        path = _write(
            tmp_path / "tests" / "test_records.py",
            "# style: ignore-file[RS065]\n" + _SETUP_SOURCE,
        )

        assert lint_path(path, {RS_REPEATED_TEST_SETUP}) == []

    def test_ParametrizationOverlap_RemainsIndependentlyVisible(
        self, tmp_path: Path
    ) -> None:
        source = (
            _SETUP_SOURCE.replace("assert saved.alpha", 'assert saved.kind == "alpha"')
            .replace("assert saved.beta", 'assert saved.kind == "beta"')
            .replace("assert saved.gamma", 'assert saved.kind == "gamma"')
        )
        path = tmp_path / "tests" / "test_records.py"

        setup = list(check_repeated_test_setup(path, source))
        parametrization = list(check_test_parametrization_candidate(path, source))

        assert len(setup) == 3
        assert len(parametrization) == 3

    def test_CallInAssignmentAnnotation_ReportsNothing(self, tmp_path: Path) -> None:
        source = """\
def test_Record_AcceptsAlpha():
    record: make_record() = 1
    saved = 2
    assert record

def test_Record_AcceptsBeta():
    record: make_record() = 1
    saved = 2
    assert saved

def test_Record_AcceptsGamma():
    record: make_record() = 1
    saved = 2
    assert record == saved
"""

        findings = check_repeated_test_setup(
            tmp_path / "tests" / "test_records.py", source
        )

        assert list(findings) == []

    def test_OverlappingPrefixes_ReportStrongestGroupOncePerTest(
        self, tmp_path: Path
    ) -> None:
        source = """\
def test_Record_AcceptsAlpha():
    record = make_record()
    saved = store(record)
    ready = prepare(saved)
    assert ready.alpha

def test_Record_AcceptsBeta():
    record = make_record()
    saved = store(record)
    ready = prepare(saved)
    assert ready.beta

def test_Record_AcceptsGamma():
    record = make_record()
    saved = store(record)
    ready = prepare(saved)
    assert ready.gamma

def test_Record_AcceptsDelta():
    record = make_record()
    saved = store(record)
    assert saved.delta
"""

        findings = list(
            check_repeated_test_setup(tmp_path / "tests" / "test_records.py", source)
        )

        assert [finding.line for finding in findings] == [1, 7, 13, 19]
        assert ["3 leading assignments" in finding.message for finding in findings] == [
            True,
            True,
            True,
            False,
        ]
        assert "2 leading assignments" in findings[-1].message


class TestTestReuseIntegration:
    @pytest.mark.parametrize(
        "rule_id",
        [
            RS_SHARED_TEST_HELPER,
            RS_TEST_PARAMETRIZATION_CANDIDATE,
            RS_REPEATED_TEST_SETUP,
        ],
    )
    def test_RegisteredRule_IsAdvisoryAndHasGuidance(self, rule_id: str) -> None:
        assert severity_of(rule_id) is Severity.WARNING
        assert resolve_enabled_rules({"select": [rule_id]}) == {rule_id}
        assert rule_doc(rule_id) is not None
        assert has_guidance(rule_id)

    def test_Baseline_Count_DropsExistingReuseWarning(self, tmp_path: Path) -> None:
        target = tmp_path / "tests" / "test_records.py"
        violation = next(check_repeated_test_setup(target, _SETUP_SOURCE))
        record = baseline.build(
            {target: [violation]}, tmp_path, frozenset({RS_REPEATED_TEST_SETUP})
        )

        assert baseline.filter_baselined(target, [violation], record, tmp_path) == []

    def test_WarningPromotion_ChangesCliExitStatus(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[tool.repostyle]\nselect = ["RS064"]\n', encoding="utf-8"
        )
        target = _write(tmp_path / "tests" / "test_parser.py", _PARAMETRIZATION_SOURCE)

        advisory_exit = main([str(target)])
        advisory_output = capsys.readouterr()
        promoted_exit = main(["--warnings-as-errors", str(target)])
        promoted_output = capsys.readouterr()

        assert advisory_exit == 0
        assert "warning: RS064" in advisory_output.out
        assert promoted_exit == 1
        assert "error: RS064" in promoted_output.out


def _helper_source(
    name: str,
    parameter: str = "value",
    local: str = "created",
    *,
    import_line: str = "from factory import make",
) -> str:
    return (
        f"{import_line}\n\n"
        f"def {name}({parameter}):\n"
        f"    {local} = make({parameter})\n"
        f"    {local}.prepare()\n"
        f"    return {local}\n"
    )


def _fixture_source(parameter: str) -> str:
    return (
        "import pytest\n\n"
        "@pytest.fixture\n"
        f"def record({parameter}):\n"
        f"    value = {parameter}.make()\n"
        "    value.prepare()\n"
        "    return value\n"
    )


def _write(path: Path, source: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def _write_config(tmp_path: Path, *, exclude: str | None = None) -> None:
    suffix = f"\nexclude = {exclude}" if exclude else ""
    (tmp_path / "pyproject.toml").write_text(
        f"[tool.repostyle]{suffix}\n", encoding="utf-8"
    )
