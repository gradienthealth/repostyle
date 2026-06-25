from pathlib import Path

import pytest

from pystyle.rules import RS_BANNED_IMPORT_BY_PATH, check_banned_import_by_path

_BANNED_TABLE = '[tool.pystyle.banned-imports]\n"src/**" = ["tests", "httpx"]\n'


def _target(
    tmp_path: Path, relative: str, source: str, table: str = _BANNED_TABLE
) -> Path:
    (tmp_path / "pyproject.toml").write_text(table, encoding="utf-8")
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")
    return target


class TestCheckBannedImportByPath:
    @pytest.mark.parametrize(
        "source",
        [
            "import tests",
            "import tests.fakes",
            "from tests.unit import helpers",
            "import httpx",
        ],
        ids=["import", "import_submodule", "from_submodule", "second_source"],
    )
    def test_BannedSourceUnderGlob_FlagsViolation(
        self, tmp_path: Path, source: str
    ) -> None:
        target = _target(tmp_path, "src/pkg/m.py", source)
        violations = list(check_banned_import_by_path(target, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_BANNED_IMPORT_BY_PATH

    @pytest.mark.parametrize(
        "source",
        ["import teststuff", "from testkit import helpers"],
        ids=["prefix_module", "prefix_from"],
    )
    def test_BannedPrefixButDistinctModule_NoViolation(
        self, tmp_path: Path, source: str
    ) -> None:
        target = _target(tmp_path, "src/pkg/m.py", source)
        assert list(check_banned_import_by_path(target, source)) == []

    def test_AllowedImportUnderGlob_NoViolation(self, tmp_path: Path) -> None:
        source = "import json\nfrom collections import OrderedDict\n"
        target = _target(tmp_path, "src/pkg/m.py", source)
        assert list(check_banned_import_by_path(target, source)) == []

    def test_BannedSourceOutsideGlob_NoViolation(self, tmp_path: Path) -> None:
        source = "import tests\n"
        target = _target(tmp_path, "scripts/m.py", source)
        assert list(check_banned_import_by_path(target, source)) == []

    def test_RelativeImport_NoViolation(self, tmp_path: Path) -> None:
        source = "from . import tests\n"
        target = _target(tmp_path, "src/pkg/m.py", source)
        assert list(check_banned_import_by_path(target, source)) == []

    def test_NoBannedImportsTable_NoViolation(self, tmp_path: Path) -> None:
        source = "import tests\n"
        target = _target(
            tmp_path, "src/pkg/m.py", source, table="[tool.other]\nx = 1\n"
        )
        assert list(check_banned_import_by_path(target, source)) == []
