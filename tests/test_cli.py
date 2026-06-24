from collections.abc import Callable
from pathlib import Path

import pytest

from gradient_pystyle.cli import main
from gradient_pystyle.rules import RS_ACRONYM_CASING, RULE_SEVERITY, Severity


def _project(tmp_path: Path, source: str, select: str) -> Path:
    (tmp_path / "pyproject.toml").write_text(
        f"[tool.gradient-pystyle]\nselect = {select}\n", encoding="utf-8"
    )
    target = tmp_path / "x.py"
    target.write_text(source, encoding="utf-8")
    return target


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
            '[tool.gradient-pystyle]\nselect = ["RS001"]\n', encoding="utf-8"
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
