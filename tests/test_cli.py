from collections.abc import Callable
from pathlib import Path

import pytest

from repostyle.cli import main
from repostyle.rules import RS_ACRONYM_CASING, RULE_SEVERITY, Severity

_ACRONYM_SOURCE = "if True:\n    class FhirClient: ...\n"


class TestMain:
    def test_ErrorViolation_PrintsSeverityLineAndFails(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _write_project(tmp_path, _ACRONYM_SOURCE, '["RS001"]')
        exit_code = main([str(target)])
        out = capsys.readouterr().out
        assert exit_code == 1
        assert f"{target}:2:5: error: RS001" in out

    def test_WarningRule_PrintsWarningAndPasses(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setitem(RULE_SEVERITY, RS_ACRONYM_CASING, Severity.WARNING)
        target = _write_project(tmp_path, _ACRONYM_SOURCE, '["RS001"]')
        exit_code = main(["--no-warnings-as-errors", str(target)])
        out = capsys.readouterr().out
        assert exit_code == 0
        assert f"{target}:2:5: warning: RS001" in out

    def test_DiffMode_ReportsOnlyChangedLineFindings(
        self,
        git_repo: Path,
        git: Callable[..., None],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        (git_repo / "pyproject.toml").write_text(
            '[tool.repostyle]\nselect = ["RS001"]\n', encoding="utf-8"
        )
        target = git_repo / "x.py"
        target.write_text("class FhirClient: ...\n", encoding="utf-8")
        git("add", "x.py", "pyproject.toml")
        git("commit", "-m", "base")
        target.write_text(
            "class FhirClient: ...\nclass JsonThing: ...\n", encoding="utf-8"
        )
        exit_code = main(["--diff", str(target)])
        out = capsys.readouterr().out
        assert exit_code == 1
        assert f"{target}:2:1: error: RS001" in out
        assert f"{target}:1:1:" not in out

    def test_DiffModeWithUnknownBase_RefusesTheRun(
        self,
        git_repo: Path,
        git: Callable[..., None],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        (git_repo / "pyproject.toml").write_text(
            '[tool.repostyle]\nselect = ["RS001"]\n', encoding="utf-8"
        )
        target = git_repo / "x.py"
        target.write_text("class FhirClient: ...\n", encoding="utf-8")
        exit_code = main(["--diff", "--diff-base", "no-such-ref", str(target)])
        captured = capsys.readouterr()
        assert exit_code == 2
        assert "cannot resolve no-such-ref" in captured.err
        assert captured.out == ""

    def test_CleanPath_ReturnsZeroAndPrintsNothing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _write_project(tmp_path, "x = 1\n", '["RS001"]')
        exit_code = main([str(target)])
        assert exit_code == 0
        assert capsys.readouterr().out == ""

    def test_DirectoryArgument_RecursesAndReportsFindings(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _write_project(tmp_path, _ACRONYM_SOURCE, '["RS001"]')
        exit_code = main([str(tmp_path)])
        out = capsys.readouterr().out
        assert exit_code == 1
        assert f"{target}:2:5: error: RS001" in out

    def test_DirectoryArgumentWithNestedPyproject_ResolvesRootConfig(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[tool.repostyle]\nselect = ["RS001"]\n', encoding="utf-8"
        )
        nested = tmp_path / "aaa_sub"
        nested.mkdir()
        (nested / "pyproject.toml").write_text(
            '[tool.repostyle]\nselect = ["RS002"]\n', encoding="utf-8"
        )
        (nested / "x.py").write_text(_ACRONYM_SOURCE, encoding="utf-8")
        exit_code = main([str(tmp_path)])
        out = capsys.readouterr().out
        assert exit_code == 1
        assert "RS001" in out

    def test_EmptyDirectoryArgument_ReturnsZeroAndPrintsNothing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        exit_code = main([str(tmp_path)])
        assert exit_code == 0
        assert capsys.readouterr().out == ""

    def test_ExcludedFile_ProducesNoFindings(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[tool.repostyle]\nselect = ["RS001"]\nexclude = ["_grpc/*.py"]\n',
            encoding="utf-8",
        )
        generated = tmp_path / "_grpc"
        generated.mkdir()
        stub = generated / "stub.py"
        stub.write_text(_ACRONYM_SOURCE, encoding="utf-8")
        exit_code = main([str(tmp_path)])
        assert exit_code == 0
        assert capsys.readouterr().out == ""

    def test_NonexistentPathArgument_ReturnsTwoAndReportsError(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        missing = tmp_path / "no_such_file.py"
        exit_code = main([str(missing)])
        captured = capsys.readouterr()
        assert exit_code == 2
        assert str(missing) in captured.err
        assert captured.out == ""

    def test_UnknownRuleId_ReturnsTwoAndReportsError(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _write_project(tmp_path, "x = 1\n", '["RS999"]')
        exit_code = main([str(target)])
        assert exit_code == 2
        assert "RS999" in capsys.readouterr().err


_IMPERATIVE_DOCSTRING = 'def f():\n    """Return the thing."""\n'


class TestErrorPromotion:
    def test_PromotedAdvisoryRule_PrintsErrorAndFails(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _write_promotion_project(
            tmp_path, _IMPERATIVE_DOCSTRING, '["RS034"]', '["RS034"]'
        )
        exit_code = main([str(target)])
        out = capsys.readouterr().out
        assert exit_code == 1
        assert f"{target}:1:1: error: RS034" in out

    def test_UnpromotedAdvisoryRule_PrintsWarningAndPasses(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _write_promotion_project(
            tmp_path, _IMPERATIVE_DOCSTRING, '["RS034"]', "[]"
        )
        exit_code = main([str(target)])
        out = capsys.readouterr().out
        assert exit_code == 0
        assert f"{target}:1:1: warning: RS034" in out

    def test_UnknownIdInError_ReturnsTwoAndReportsError(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _write_promotion_project(tmp_path, "x = 1\n", '["RS001"]', '["RS999"]')
        exit_code = main([str(target)])
        assert exit_code == 2
        assert "RS999" in capsys.readouterr().err

    def test_PromotingNativelyErrorRule_IsNoOp(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _write_promotion_project(
            tmp_path, _ACRONYM_SOURCE, '["RS001"]', '["RS001"]'
        )
        exit_code = main([str(target)])
        out = capsys.readouterr().out
        assert exit_code == 1
        assert f"{target}:2:5: error: RS001" in out


class TestWarningsAsErrors:
    def test_ConfigKey_PrintsAdvisoryFindingAsErrorAndFails(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _write_promotion_project(
            tmp_path, _IMPERATIVE_DOCSTRING, '["RS034"]', "[]", warnings_as_errors=True
        )
        exit_code = main([str(target)])
        out = capsys.readouterr().out
        assert exit_code == 1
        assert f"{target}:1:1: error: RS034" in out

    def test_Flag_PromotesWithoutConfig(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _write_promotion_project(
            tmp_path, _IMPERATIVE_DOCSTRING, '["RS034"]', "[]"
        )
        exit_code = main(["--warnings-as-errors", str(target)])
        out = capsys.readouterr().out
        assert exit_code == 1
        assert f"{target}:1:1: error: RS034" in out

    def test_ToleratedWarning_CountsItOnStderr(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _write_promotion_project(
            tmp_path, _IMPERATIVE_DOCSTRING, '["RS034"]', "[]"
        )
        exit_code = main([str(target)])
        err = capsys.readouterr().err
        assert exit_code == 0
        assert "1 warning(s) reported without failing the run" in err

    def test_NoToleratedWarning_SaysNothing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _write_promotion_project(tmp_path, "x = 1\n", '["RS034"]', "[]")
        exit_code = main([str(target)])
        err = capsys.readouterr().err
        assert exit_code == 0
        assert "without failing the run" not in err


_UNDERWRAPPED_DOCSTRING = 'def f():\n    """Summary.\n\n    aaa\n    bbb\n    """\n'


class TestFix:
    def test_FixWithChanges_ExitsNonzeroAndReportsToStderr(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _write_project(tmp_path, _UNDERWRAPPED_DOCSTRING, '["RS009"]')
        exit_code = main(["--fix", str(target)])
        captured = capsys.readouterr()
        assert exit_code == 1
        assert "fixed" in captured.err
        assert str(target) in captured.err

    def test_FixOnFilledFile_ExitsZeroAndIsSilent(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        source = 'def f():\n    """Summary.\n\n    aaa bbb\n    """\n'
        target = _write_project(tmp_path, source, '["RS009"]')
        exit_code = main(["--fix", str(target)])
        captured = capsys.readouterr()
        assert exit_code == 0
        assert captured.err == ""

    def test_WithoutFix_ReportsButDoesNotRewrite(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _write_project(tmp_path, _UNDERWRAPPED_DOCSTRING, '["RS009"]')
        exit_code = main([str(target)])
        assert exit_code == 1
        assert target.read_text(encoding="utf-8") == _UNDERWRAPPED_DOCSTRING
        assert "under-wrapped" in capsys.readouterr().out

    def test_FixThenReport_ReportsTheRewrittenFile(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _write_project(tmp_path, _UNDERWRAPPED_DOCSTRING, '["RS009"]')
        main(["--fix", str(target)])
        assert "under-wrapped" not in capsys.readouterr().out


class TestExplain:
    def test_KnownRule_PrintsCardAndReturnsZero(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        exit_code = main(["explain", "RS010"])
        out = capsys.readouterr().out
        assert exit_code == 0
        assert "RS010  banned-abbreviation" in out
        assert "Reference:" in out

    def test_All_PrintsEveryCard(self, capsys: pytest.CaptureFixture[str]) -> None:
        exit_code = main(["explain", "--all"])
        out = capsys.readouterr().out
        assert exit_code == 0
        assert "RS001  acronym-casing" in out
        assert "RS031  arg-described-in-prose" in out

    def test_UnknownRule_ReturnsTwoAndReportsToStderr(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        exit_code = main(["explain", "RS999"])
        captured = capsys.readouterr()
        assert exit_code == 2
        assert "RS999" in captured.err
        assert captured.out == ""

    def test_NoRuleId_ExitsWithUsageError(self) -> None:
        with pytest.raises(SystemExit) as raised:
            main(["explain"])
        assert raised.value.code == 2


class TestDiscoveryHint:
    def test_FindingWithGuidance_PrintsTheExplainHintToStderr(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _write_project(tmp_path, "def f(cfg): ...\n", '["RS010"]')
        exit_code = main([str(target)])
        captured = capsys.readouterr()
        assert exit_code == 1
        assert "→ run 'repostyle explain RS010'" in captured.err

    def test_NoExplainHintFlag_SuppressesTheHint(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _write_project(tmp_path, "def f(cfg): ...\n", '["RS010"]')
        main(["--no-explain-hint", str(target)])
        assert "explain RS010" not in capsys.readouterr().err

    def test_FindingWithoutGuidance_PrintsNoHint(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        source = 'class C:\n    """Doc.\n\n    Attributes:\n        a: int.\n    """\n'
        target = _write_project(tmp_path, source, '["RS004"]')
        main([str(target)])
        assert "explain" not in capsys.readouterr().err


_TWO_ACRONYM_CLASSES = "class FhirClient: ...\nclass JsonThing: ...\n"


class TestBaseline:
    def test_WrittenBaseline_GrandfathersTheTree(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _write_project(tmp_path, _TWO_ACRONYM_CLASSES, '["RS001"]')
        assert main(["--write-baseline", str(tmp_path)]) == 0
        capsys.readouterr()
        exit_code = main([str(target)])
        assert exit_code == 0
        assert capsys.readouterr().out == ""

    def test_FindingBeyondTheBaseline_StillFails(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _write_project(tmp_path, _TWO_ACRONYM_CLASSES, '["RS001"]')
        main(["--write-baseline", str(tmp_path)])
        capsys.readouterr()
        target.write_text(
            _TWO_ACRONYM_CLASSES + "class JwtThing: ...\n", encoding="utf-8"
        )
        exit_code = main([str(target)])
        assert exit_code == 1
        assert "RS001" in capsys.readouterr().out

    def test_NoBaselineFlag_ReportsTheGrandfatheredFindings(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _write_project(tmp_path, _TWO_ACRONYM_CLASSES, '["RS001"]')
        main(["--write-baseline", str(tmp_path)])
        capsys.readouterr()
        exit_code = main(["--no-baseline", str(target)])
        assert exit_code == 1
        assert capsys.readouterr().out.count("RS001") == 2

    def test_UpdateBaseline_DropsFindingsSinceFixed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _write_project(tmp_path, _TWO_ACRONYM_CLASSES, '["RS001"]')
        main(["--write-baseline", str(tmp_path)])
        target.write_text("class FHIRClient: ...\nclass JsonThing: ...\n", "utf-8")
        main(["--update-baseline", str(tmp_path)])
        capsys.readouterr()
        target.write_text(_TWO_ACRONYM_CLASSES, encoding="utf-8")
        exit_code = main([str(target)])
        assert exit_code == 1
        assert capsys.readouterr().out.count("RS001") == 1

    def test_UpdateBaseline_RefusesToGrandfatherNewFindings(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _write_project(tmp_path, _TWO_ACRONYM_CLASSES, '["RS001"]')
        main(["--write-baseline", str(tmp_path)])
        target.write_text(
            _TWO_ACRONYM_CLASSES + "class JwtThing: ...\n", encoding="utf-8"
        )
        main(["--update-baseline", str(tmp_path)])
        capsys.readouterr()
        exit_code = main([str(target)])
        assert exit_code == 1
        assert capsys.readouterr().out.count("RS001") == 1

    def test_UnreadableBaseline_ReportsEverythingAndSaysSo(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _write_project(tmp_path, _TWO_ACRONYM_CLASSES, '["RS001"]')
        (tmp_path / ".repostyle-baseline.json").write_text("{oops", encoding="utf-8")
        exit_code = main([str(target)])
        captured = capsys.readouterr()
        assert exit_code == 1
        assert "unreadable baseline" in captured.err
        assert captured.out.count("RS001") == 2


class TestWarningsAsErrorsDefault:
    def test_AdvisoryRuleWithNoConfig_FailsTheRun(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _write_project(tmp_path, _IMPERATIVE_DOCSTRING, '["RS034"]')
        exit_code = main([str(target)])
        out = capsys.readouterr().out
        assert exit_code == 1
        assert f"{target}:1:1: error: RS034" in out

    def test_OptOutInConfig_RestoresTheDefaultSeverity(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _write_promotion_project(
            tmp_path, _IMPERATIVE_DOCSTRING, '["RS034"]', "[]"
        )
        exit_code = main([str(target)])
        out = capsys.readouterr().out
        assert exit_code == 0
        assert f"{target}:1:1: warning: RS034" in out

    def test_OptOutFlag_RestoresTheDefaultSeverity(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _write_project(tmp_path, _IMPERATIVE_DOCSTRING, '["RS034"]')
        exit_code = main(["--no-warnings-as-errors", str(target)])
        out = capsys.readouterr().out
        assert exit_code == 0
        assert f"{target}:1:1: warning: RS034" in out


class TestDiffDeprecation:
    def test_DiffFlag_SaysItIsDeprecated(
        self,
        git_repo: Path,
        git: Callable[..., None],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        (git_repo / "pyproject.toml").write_text(
            '[tool.repostyle]\nselect = ["RS001"]\n', encoding="utf-8"
        )
        target = git_repo / "x.py"
        target.write_text("class FhirClient: ...\n", encoding="utf-8")
        git("add", "x.py", "pyproject.toml")
        git("commit", "-m", "base")
        main(["--diff", "--diff-base", "HEAD", str(target)])
        assert "--diff is deprecated" in capsys.readouterr().err

    def test_WithoutDiffFlag_SaysNothing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _write_project(tmp_path, _ACRONYM_SOURCE, '["RS001"]')
        main([str(target)])
        assert "deprecated" not in capsys.readouterr().err


def _write_project(tmp_path: Path, source: str, select: str) -> Path:
    (tmp_path / "pyproject.toml").write_text(
        f"[tool.repostyle]\nselect = {select}\n", encoding="utf-8"
    )
    target = tmp_path / "x.py"
    target.write_text(source, encoding="utf-8")
    return target


def _write_promotion_project(
    tmp_path: Path,
    source: str,
    select: str,
    error: str,
    *,
    warnings_as_errors: bool = False,
) -> Path:
    switch = f"warnings-as-errors = {str(warnings_as_errors).lower()}\n"
    (tmp_path / "pyproject.toml").write_text(
        f"[tool.repostyle]\nselect = {select}\nerror = {error}\n{switch}",
        encoding="utf-8",
    )
    target = tmp_path / "x.py"
    target.write_text(source, encoding="utf-8")
    return target
