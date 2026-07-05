from pathlib import Path

import pytest

from repostyle.rules import (
    RS_FILENAME_CONVENTION,
    check_filename_casing,
    check_filename_extension,
)

_SOURCE = "irrelevant: true\n"


class TestCheckFilenameExtension:
    def test_DefaultMappedExtension_FlagsViolation(self, tmp_path: Path) -> None:
        target = _target(tmp_path, "config.yml")
        violations = list(check_filename_extension(target, _SOURCE))
        assert len(violations) == 1
        assert violations[0].rule == RS_FILENAME_CONVENTION

    def test_AlreadyPreferredExtension_NoViolation(self, tmp_path: Path) -> None:
        target = _target(tmp_path, "config.yaml")
        assert list(check_filename_extension(target, _SOURCE)) == []

    def test_ConfiguredMapping_FlagsConfiguredExtension(self, tmp_path: Path) -> None:
        table = '[tool.repostyle.filename-extensions]\n".txt" = ".md"\n'
        target = _target(tmp_path, "notes.txt", table=table)
        violations = list(check_filename_extension(target, _SOURCE))
        assert len(violations) == 1
        assert violations[0].rule == RS_FILENAME_CONVENTION

    def test_ConfiguredMappingReplacesDefault_NoViolationForYml(
        self, tmp_path: Path
    ) -> None:
        table = '[tool.repostyle.filename-extensions]\n".txt" = ".md"\n'
        target = _target(tmp_path, "config.yml", table=table)
        assert list(check_filename_extension(target, _SOURCE)) == []

    def test_EmptyConfiguredMapping_DisablesCheck(self, tmp_path: Path) -> None:
        table = "[tool.repostyle.filename-extensions]\n"
        target = _target(tmp_path, "config.yml", table=table)
        assert list(check_filename_extension(target, _SOURCE)) == []

    def test_NonDictConfiguredMapping_DisablesCheck(self, tmp_path: Path) -> None:
        table = "[tool.repostyle]\nfilename-extensions = []\n"
        target = _target(tmp_path, "config.yml", table=table)
        assert list(check_filename_extension(target, _SOURCE)) == []

    def test_IgnoredGlob_NoViolation(self, tmp_path: Path) -> None:
        table = '[tool.repostyle]\nfilename-ignore = ["config.yml"]\n'
        target = _target(tmp_path, "config.yml", table=table)
        assert list(check_filename_extension(target, _SOURCE)) == []

    def test_BareStringIgnoreGlob_TreatsAsSingleGlob(self, tmp_path: Path) -> None:
        table = '[tool.repostyle]\nfilename-ignore = "config.yml"\n'
        target = _target(tmp_path, "config.yml", table=table)
        assert list(check_filename_extension(target, _SOURCE)) == []

    def test_PythonFile_NoViolation(self, tmp_path: Path) -> None:
        target = _target(tmp_path, "config.py")
        assert list(check_filename_extension(target, "x = 1\n")) == []


class TestCheckFilenameCasing:
    @pytest.mark.parametrize(
        "name",
        ["my_config.yaml", "MyConfig.yaml", "my_config.toml"],
        ids=["snake_case", "PascalCase", "toml_snake_case"],
    )
    def test_NonKebabName_FlagsViolation(self, tmp_path: Path, name: str) -> None:
        target = _target(tmp_path, name)
        violations = list(check_filename_casing(target, _SOURCE))
        assert len(violations) == 1
        assert violations[0].rule == RS_FILENAME_CONVENTION

    @pytest.mark.parametrize(
        "name",
        ["my-config.yaml", "config.yaml", ".pre-commit-config.yaml"],
        ids=["kebab_case", "single_word", "dotfile_kebab"],
    )
    def test_KebabName_NoViolation(self, tmp_path: Path, name: str) -> None:
        target = _target(tmp_path, name)
        assert list(check_filename_casing(target, _SOURCE)) == []

    def test_ConfiguredSnakeCase_FlagsHyphenatedName(self, tmp_path: Path) -> None:
        table = '[tool.repostyle]\nfilename-case = "snake"\n'
        target = _target(tmp_path, "my-config.yaml", table=table)
        violations = list(check_filename_casing(target, _SOURCE))
        assert len(violations) == 1
        assert violations[0].rule == RS_FILENAME_CONVENTION

    def test_ConfiguredSnakeCase_NoViolationForUnderscoredName(
        self, tmp_path: Path
    ) -> None:
        table = '[tool.repostyle]\nfilename-case = "snake"\n'
        target = _target(tmp_path, "my_config.yaml", table=table)
        assert list(check_filename_casing(target, _SOURCE)) == []

    def test_ConfiguredCaseIsCaseInsensitive(self, tmp_path: Path) -> None:
        table = '[tool.repostyle]\nfilename-case = "SNAKE"\n'
        target = _target(tmp_path, "my-config.yaml", table=table)
        violations = list(check_filename_casing(target, _SOURCE))
        assert len(violations) == 1
        assert violations[0].rule == RS_FILENAME_CONVENTION

    def test_ConfiguredNone_DisablesCheck(self, tmp_path: Path) -> None:
        table = '[tool.repostyle]\nfilename-case = "none"\n'
        target = _target(tmp_path, "MyConfig.yaml", table=table)
        assert list(check_filename_casing(target, _SOURCE)) == []

    def test_IgnoredGlob_NoViolation(self, tmp_path: Path) -> None:
        table = '[tool.repostyle]\nfilename-ignore = ["README.md"]\n'
        target = _target(tmp_path, "README.md", table=table)
        assert list(check_filename_casing(target, _SOURCE)) == []

    def test_PythonFile_NoViolation(self, tmp_path: Path) -> None:
        target = _target(tmp_path, "MyConfig.py")
        assert list(check_filename_casing(target, "x = 1\n")) == []


def _target(tmp_path: Path, name: str, table: str = "") -> Path:
    if table:
        (tmp_path / "pyproject.toml").write_text(table, encoding="utf-8")
    target = tmp_path / name
    target.write_text(_SOURCE, encoding="utf-8")
    return target
