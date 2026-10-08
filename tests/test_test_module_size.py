from collections.abc import Callable
from pathlib import Path

import pytest

from repostyle import baseline
from repostyle.cli import main
from repostyle.rules import (
    RS_ACRONYM_CASING,
    RS_SOURCE_MODULE_SIZE,
    RS_TEST_MODULE_SIZE,
    Severity,
    check_source_module_size,
    check_test_module_size,
    severity_of,
)
from repostyle.runner import lint_path


class TestCheckTestModuleSize:
    @pytest.mark.parametrize(
        ("line_count", "expected_count"),
        [(500, 0), (501, 1)],
        ids=["at-limit", "over-limit"],
    )
    def test_DefaultLimit_UsesStrictBoundary(
        self, tmp_path: Path, line_count: int, expected_count: int
    ) -> None:
        source = _assignment_lines(line_count)
        target = tmp_path / "tests" / "test_x.py"
        violations = list(check_test_module_size(target, source))
        assert len(violations) == expected_count
        assert [item.rule for item in violations] == [
            RS_TEST_MODULE_SIZE
        ] * expected_count
        assert (
            sum("501 code lines (limit: 500)" in item.message for item in violations)
            == expected_count
        )

    def test_DocstringsCommentsAndBlanks_DoNotCount(self, tmp_path: Path) -> None:
        target = _configured_target(tmp_path, 3, "tests/test_x.py")
        source = (
            '"""Module\nnotes.\n"""\n'
            "\n"
            "# comment only\n"
            "class TestThing:\n"
            '    """Class notes."""\n'
            "    def test_Thing_Works(self):\n"
            '        """Function notes."""\n'
            "        assert True  # trailing comment\n"
        )
        assert list(check_test_module_size(target, source)) == []

    @pytest.mark.parametrize(
        "source",
        [
            '(\n    "Module "\n    "notes."\n)\nvalue = 1\n',
            "class TestThing:\n"
            "    (\n"
            '        "Class "\n'
            '        "notes."\n'
            "    )\n"
            "    value = 1\n",
        ],
        ids=["module", "class"],
    )
    def test_ParenthesizedConcatenatedDocstring_DoesNotCount(
        self, tmp_path: Path, source: str
    ) -> None:
        target = _configured_target(tmp_path, 2, "tests/test_x.py")
        assert list(check_test_module_size(target, source)) == []

    def test_CodeSharingLineWithDocstring_Counts(self, tmp_path: Path) -> None:
        target = _configured_target(tmp_path, 1, "tests/helpers.py")
        source = 'def helper(): "doc"; return 1\nvalue = 1\n'
        violations = list(check_test_module_size(target, source))
        assert "2 code lines (limit: 1)" in violations[0].message

    def test_MultilineDataAndStructuralLines_Count(self, tmp_path: Path) -> None:
        target = _configured_target(tmp_path, 1, "tests/test_x.py")
        source = 'DATA = """first\nsecond\nthird"""\n'
        violations = list(check_test_module_size(target, source))
        assert "3 code lines (limit: 1)" in violations[0].message

    def test_UnicodeSeparatorInsideString_DoesNotShiftLaterLines(
        self, tmp_path: Path
    ) -> None:
        target = _configured_target(tmp_path, 2, "tests/test_x.py")
        source = 'DATA = """first\u2028second"""\nvalue = 1\nother = 2\n'
        violations = list(check_test_module_size(target, source))
        assert "3 code lines (limit: 2)" in violations[0].message

    def test_DecoratorsFixturesHelpersAndParameterTables_Count(
        self, tmp_path: Path
    ) -> None:
        target = _configured_target(tmp_path, 1, "tests/helpers.py")
        source = (
            "@pytest.fixture\n"
            "def patients():\n"
            "    return [\n"
            '        ("Ada", 36),\n'
            '        ("Lin", 42),\n'
            "    ]\n"
        )
        violations = list(check_test_module_size(target, source))
        assert "6 code lines (limit: 1)" in violations[0].message

    def test_MixedCodeAndComments_CountOnlyCodeLine(self, tmp_path: Path) -> None:
        target = _configured_target(tmp_path, 1, "tests/test_x.py")
        source = "# comment only\nvalue = 1  # trailing comment\n# another comment\n"
        assert list(check_test_module_size(target, source)) == []

    @pytest.mark.parametrize(
        "relative",
        ["tests/helpers.py", "tests/conftest.py", "test_widget.py"],
        ids=["helper-under-tests", "conftest", "test-filename"],
    )
    def test_TestFileScope_ChecksPythonTestSupportFiles(
        self, tmp_path: Path, relative: str
    ) -> None:
        target = _configured_target(tmp_path, 1, relative)
        assert len(list(check_test_module_size(target, "a = 1\nb = 2\n"))) == 1

    def test_ProductionFile_IsOutsideScope(self, tmp_path: Path) -> None:
        target = _configured_target(tmp_path, 1, "src/widget.py")
        assert list(check_test_module_size(target, "a = 1\nb = 2\n")) == []

    def test_InvalidPython_IsNotChecked(self, tmp_path: Path) -> None:
        target = _configured_target(tmp_path, 1, "tests/test_x.py")
        assert list(check_test_module_size(target, "def broken(:\n")) == []

    def test_CustomLimit_OverridesDefault(self, tmp_path: Path) -> None:
        target = _configured_target(tmp_path, 2, "tests/test_x.py")
        violations = list(check_test_module_size(target, _assignment_lines(3)))
        assert "3 code lines (limit: 2)" in violations[0].message

    @pytest.mark.parametrize(
        "configured",
        ["0", "-1", "true", '"500"', "500.0"],
        ids=["zero", "negative", "boolean", "string", "float"],
    )
    def test_InvalidLimit_RaisesValueError(
        self, tmp_path: Path, configured: str
    ) -> None:
        target = _configured_target(tmp_path, configured, "tests/test_x.py")
        with pytest.raises(ValueError, match="must be a positive integer"):
            list(check_test_module_size(target, "a = 1\nb = 2\n"))

    def test_FindingPointsToFirstCodeLine(self, tmp_path: Path) -> None:
        target = _configured_target(tmp_path, 1, "tests/test_x.py")
        source = '# heading\n"""Module notes."""\n\nimport pytest\nvalue = 1\n'
        violations = list(check_test_module_size(target, source))
        assert [(item.line, item.col) for item in violations] == [(4, 1)]

    def test_ThresholdRule_IsWarning(self) -> None:
        assert severity_of(RS_TEST_MODULE_SIZE) is Severity.WARNING


class TestCheckSourceModuleSize:
    @pytest.mark.parametrize(
        ("line_count", "expected_count"),
        [(250, 0), (251, 1)],
        ids=["at-limit", "over-limit"],
    )
    def test_DefaultLimit_UsesStrictBoundary(
        self, tmp_path: Path, line_count: int, expected_count: int
    ) -> None:
        source = _assignment_lines(line_count)
        target = tmp_path / "src" / "package" / "widget.py"
        violations = list(check_source_module_size(target, source))
        assert len(violations) == expected_count
        assert [item.rule for item in violations] == [
            RS_SOURCE_MODULE_SIZE
        ] * expected_count
        assert (
            sum("251 code lines (limit: 250)" in item.message for item in violations)
            == expected_count
        )

    @pytest.mark.parametrize(
        "relative",
        [
            "tests/helpers.py",
            "src/package/test_widget.py",
            "src/package/widget_test.py",
        ],
        ids=["tests-directory", "test-prefix", "test-suffix"],
    )
    def test_TestModuleScope_IsExcluded(self, tmp_path: Path, relative: str) -> None:
        target = _configured_source_target(tmp_path, 1, relative)
        assert list(check_source_module_size(target, "a = 1\nb = 2\n")) == []

    @pytest.mark.parametrize(
        "relative",
        ["src/package/widget.py", "src/package/__init__.py"],
        ids=["ordinary-module", "package-initializer"],
    )
    def test_SourceModuleScope_ChecksPythonModules(
        self, tmp_path: Path, relative: str
    ) -> None:
        target = _configured_source_target(tmp_path, 1, relative)
        assert len(list(check_source_module_size(target, "a = 1\nb = 2\n"))) == 1

    def test_StubFile_IsOutsideCurrentPythonScope(self, tmp_path: Path) -> None:
        target = _configured_source_target(tmp_path, 1, "src/package/widget.pyi")
        assert list(check_source_module_size(target, "a = 1\nb = 2\n")) == []

    def test_CustomLimit_OverridesDefault(self, tmp_path: Path) -> None:
        target = _configured_source_target(tmp_path, 2, "src/package/widget.py")
        violations = list(check_source_module_size(target, _assignment_lines(3)))
        assert "3 code lines (limit: 2)" in violations[0].message

    @pytest.mark.parametrize(
        "configured",
        ["0", "-1", "true", '"250"', "250.0"],
        ids=["zero", "negative", "boolean", "string", "float"],
    )
    def test_InvalidLimit_RaisesValueError(
        self, tmp_path: Path, configured: str
    ) -> None:
        target = _configured_source_target(
            tmp_path, configured, "src/package/widget.py"
        )
        with pytest.raises(ValueError, match="must be a positive integer"):
            list(check_source_module_size(target, "a = 1\nb = 2\n"))

    def test_DocstringsCommentsAndData_UseSharedCount(self, tmp_path: Path) -> None:
        target = _configured_source_target(tmp_path, 2, "src/package/widget.py")
        source = (
            '"""Module\nnotes.\n"""\n'
            "# comment only\n"
            'DATA = """first\nsecond\nthird"""\n'
        )
        violations = list(check_source_module_size(target, source))
        assert "3 code lines (limit: 2)" in violations[0].message

    def test_FieldDocstrings_DoNotCount(self, tmp_path: Path) -> None:
        target = _configured_source_target(tmp_path, 3, "src/package/widget.py")
        source = (
            "class Verdict:\n"
            "    skip_reason: str\n"
            '    """Why the series\n    was skipped.\n    """\n'
            "    limit = 3\n"
            '    """The cap."""\n'
        )
        assert list(check_source_module_size(target, source)) == []

    def test_FindingPointsToFirstCodeLine(self, tmp_path: Path) -> None:
        target = _configured_source_target(tmp_path, 1, "src/package/widget.py")
        source = '# heading\n"""Module notes."""\n\nimport json\nvalue = 1\n'
        violations = list(check_source_module_size(target, source))
        assert [(item.line, item.col) for item in violations] == [(4, 1)]

    def test_ThresholdRule_IsWarning(self) -> None:
        assert severity_of(RS_SOURCE_MODULE_SIZE) is Severity.WARNING


class TestTestModuleSizeIntegration:
    def test_FileSuppression_DropsOnlyModuleSizeFinding(self, tmp_path: Path) -> None:
        target = _configured_target(tmp_path, 1, "tests/test_x.py")
        target.parent.mkdir(parents=True)
        target.write_text(
            "# style: ignore-file[RS062]\nclass FhirClient: ...\nvalue = 1\n",
            encoding="utf-8",
        )
        rules = {
            finding.rule
            for finding in lint_path(target, {RS_TEST_MODULE_SIZE, RS_ACRONYM_CASING})
        }
        assert rules == {RS_ACRONYM_CASING}

    def test_GrowthAfterBaseline_RemainsGrandfathered(self, tmp_path: Path) -> None:
        target = _configured_target(tmp_path, 1, "tests/test_x.py")
        initial = list(check_test_module_size(target, _assignment_lines(2)))
        grandfathered = baseline.build(
            {target: initial}, tmp_path, frozenset({RS_TEST_MODULE_SIZE})
        )
        grown = list(check_test_module_size(target, _assignment_lines(3)))
        assert baseline.filter_baselined(target, grown, grandfathered, tmp_path) == []

    def test_DiffMode_UsesFirstCodeLineAsFindingLocation(
        self,
        git_repo: Path,
        git: Callable[..., None],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        (git_repo / "pyproject.toml").write_text(
            '[tool.repostyle]\nselect = ["RS062"]\nmax-test-file-lines = 2\n',
            encoding="utf-8",
        )
        tests = git_repo / "tests"
        tests.mkdir()
        target = tests / "test_x.py"
        target.write_text("a = 1\nb = 2\nc = 3\n", encoding="utf-8")
        git("add", "pyproject.toml", "tests/test_x.py")
        git("commit", "-m", "base")
        target.write_text("a = 1\nb = 2\nc = 4\n", encoding="utf-8")

        exit_code = main(["--diff", "--diff-base", "HEAD", str(target)])

        captured = capsys.readouterr()
        assert exit_code == 0
        assert "RS062" not in captured.out
        assert "--diff is deprecated" in captured.err


class TestSourceModuleSizeIntegration:
    @pytest.mark.parametrize(
        "directive",
        ["# style: ignore-file[RS066]\n", "a = 1  # style: ignore[RS066]\n"],
        ids=["file", "finding-line"],
    )
    def test_Suppression_DropsOnlySourceModuleSizeFinding(
        self, tmp_path: Path, directive: str
    ) -> None:
        target = _configured_source_target(tmp_path, 1, "src/fhir_client.py")
        target.parent.mkdir(parents=True)
        source = (
            f"{directive}class FhirClient: ...\nvalue = 1\n"
            if directive.startswith("#")
            else f"{directive}class FhirClient: ...\n"
        )
        target.write_text(source, encoding="utf-8")
        rules = {
            finding.rule
            for finding in lint_path(target, {RS_SOURCE_MODULE_SIZE, RS_ACRONYM_CASING})
        }
        assert rules == {RS_ACRONYM_CASING}

    def test_GrowthAfterBaseline_RemainsGrandfathered(self, tmp_path: Path) -> None:
        target = _configured_source_target(tmp_path, 1, "src/package/widget.py")
        initial = list(check_source_module_size(target, _assignment_lines(2)))
        grandfathered = baseline.build(
            {target: initial}, tmp_path, frozenset({RS_SOURCE_MODULE_SIZE})
        )
        grown = list(check_source_module_size(target, _assignment_lines(3)))
        assert baseline.filter_baselined(target, grown, grandfathered, tmp_path) == []


def _assignment_lines(count: int) -> str:
    """Returns `count` distinct assignment lines."""
    return "".join(f"value_{index} = {index}\n" for index in range(count))


def _configured_source_target(tmp_path: Path, limit: int | str, relative: str) -> Path:
    """Writes the source-module limit and returns its target path."""
    (tmp_path / "pyproject.toml").write_text(
        f"[tool.repostyle]\nmax-source-file-lines = {limit}\n", encoding="utf-8"
    )
    return tmp_path / relative


def _configured_target(tmp_path: Path, limit: int | str, relative: str) -> Path:
    """Writes the test-module limit and returns its target path."""
    (tmp_path / "pyproject.toml").write_text(
        f"[tool.repostyle]\nmax-test-file-lines = {limit}\n", encoding="utf-8"
    )
    return tmp_path / relative
