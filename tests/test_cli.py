from collections.abc import Callable
from pathlib import Path

import pytest

from pystyle.cli import main
from pystyle.rules import RS_ACRONYM_CASING, RULE_SEVERITY, Severity

_ACRONYM_SOURCE = "if True:\n    class FhirClient: ...\n"


class TestMain:
    def test_ErrorViolation_PrintsSeverityLineAndFails(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _project(tmp_path, _ACRONYM_SOURCE, '["RS001"]')
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
        target = _project(tmp_path, _ACRONYM_SOURCE, '["RS001"]')
        exit_code = main([str(target)])
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
            '[tool.pystyle]\nselect = ["RS001"]\n', encoding="utf-8"
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

    def test_DiffModeWithUnknownBase_ReportsEveryFinding(
        self,
        git_repo: Path,
        git: Callable[..., None],
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        (git_repo / "pyproject.toml").write_text(
            '[tool.pystyle]\nselect = ["RS001"]\n', encoding="utf-8"
        )
        target = git_repo / "x.py"
        target.write_text("class FhirClient: ...\n", encoding="utf-8")
        exit_code = main(["--diff", "--diff-base", "no-such-ref", str(target)])
        out = capsys.readouterr().out
        assert exit_code == 1
        assert f"{target}:1:1: error: RS001" in out

    def test_CleanPath_ReturnsZeroAndPrintsNothing(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _project(tmp_path, "x = 1\n", '["RS001"]')
        exit_code = main([str(target)])
        assert exit_code == 0
        assert capsys.readouterr().out == ""

    def test_UnknownRuleId_ReturnsTwoAndReportsError(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _project(tmp_path, "x = 1\n", '["RS999"]')
        exit_code = main([str(target)])
        assert exit_code == 2
        assert "RS999" in capsys.readouterr().err


_UNDERWRAPPED_DOCSTRING = 'def f():\n    """Summary.\n\n    aaa\n    bbb\n    """\n'


class TestFix:
    def test_FixWithChanges_ExitsNonzeroAndReportsToStderr(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _project(tmp_path, _UNDERWRAPPED_DOCSTRING, '["RS009"]')
        exit_code = main(["--fix", str(target)])
        captured = capsys.readouterr()
        assert exit_code == 1
        assert "reflowed" in captured.err and str(target) in captured.err

    def test_FixOnFilledFile_ExitsZeroAndIsSilent(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        source = 'def f():\n    """Summary.\n\n    aaa bbb\n    """\n'
        target = _project(tmp_path, source, '["RS009"]')
        exit_code = main(["--fix", str(target)])
        captured = capsys.readouterr()
        assert exit_code == 0
        assert captured.err == ""

    def test_WithoutFix_ReportsButDoesNotRewrite(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _project(tmp_path, _UNDERWRAPPED_DOCSTRING, '["RS009"]')
        exit_code = main([str(target)])
        assert exit_code == 1
        assert target.read_text(encoding="utf-8") == _UNDERWRAPPED_DOCSTRING
        assert "under-wrapped" in capsys.readouterr().out


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
        target = _project(tmp_path, "def f(cfg): ...\n", '["RS010"]')
        exit_code = main([str(target)])
        captured = capsys.readouterr()
        assert exit_code == 1
        assert "→ run 'pystyle explain RS010'" in captured.err

    def test_NoExplainHintFlag_SuppressesTheHint(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _project(tmp_path, "def f(cfg): ...\n", '["RS010"]')
        main(["--no-explain-hint", str(target)])
        assert "explain RS010" not in capsys.readouterr().err

    def test_FindingWithoutGuidance_PrintsNoHint(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        target = _project(tmp_path, _ACRONYM_SOURCE, '["RS001"]')
        main([str(target)])
        assert "explain" not in capsys.readouterr().err


def _project(tmp_path: Path, source: str, select: str) -> Path:
    (tmp_path / "pyproject.toml").write_text(
        f"[tool.pystyle]\nselect = {select}\n", encoding="utf-8"
    )
    target = tmp_path / "x.py"
    target.write_text(source, encoding="utf-8")
    return target
