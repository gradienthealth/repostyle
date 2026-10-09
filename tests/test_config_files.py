from pathlib import Path

from repostyle.runner import (
    expand_paths,
    repo_root,
    resolve_baseline_path,
    resolve_rules_for_paths,
)


class TestRepostyleToml:
    def test_TopLevelSettings_ConfigureTheRun(self, tmp_path: Path) -> None:
        (tmp_path / "repostyle.toml").write_text(
            'select = ["RS001"]\nlanguages = ["java"]\n', encoding="utf-8"
        )
        java = tmp_path / "Widget.java"
        java.write_text("class Widget {}\n", encoding="utf-8")
        (tmp_path / "tool.py").write_text("x = 1\n", encoding="utf-8")
        assert resolve_rules_for_paths([tmp_path]).enabled == {"RS001"}
        assert expand_paths([tmp_path]) == [java]

    def test_BesidePyproject_TakesPrecedence(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[tool.repostyle]\nselect = ["RS002"]\n', encoding="utf-8"
        )
        (tmp_path / "repostyle.toml").write_text(
            'select = ["RS001"]\n', encoding="utf-8"
        )
        assert resolve_rules_for_paths([tmp_path]).enabled == {"RS001"}

    def test_ItsDirectory_AnchorsTheBaseline(self, tmp_path: Path) -> None:
        (tmp_path / "repostyle.toml").write_text(
            'baseline = "style-baseline.json"\n', encoding="utf-8"
        )
        nested = tmp_path / "src"
        nested.mkdir()
        assert repo_root([nested]) == tmp_path
        assert resolve_baseline_path([nested]) == tmp_path / "style-baseline.json"
