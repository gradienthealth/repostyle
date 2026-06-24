from pathlib import Path

import pytest

from gradient_pystyle.cli import main


def _project(tmp_path: Path, source: str, select: str) -> Path:
    (tmp_path / "pyproject.toml").write_text(
        f"[tool.gradient-pystyle]\nselect = {select}\n", encoding="utf-8"
    )
    target = tmp_path / "x.py"
    target.write_text(source, encoding="utf-8")
    return target


class TestMain:
    def test_Violation_PrintsLineColRuleMessage(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        source = "if True:\n    class FhirClient: ...\n"
        target = _project(tmp_path, source, '["RS001"]')
        exit_code = main([str(target)])
        out = capsys.readouterr().out
        assert exit_code == 1
        assert f"{target}:2:5: RS001" in out

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
