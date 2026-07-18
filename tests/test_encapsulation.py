from pathlib import Path

import pytest

from repostyle.rules import RS_PRIVATE_IMPORT, check_private_import


class TestCheckPrivateImport:
    @pytest.mark.parametrize(
        "source",
        [
            "from myapp.core import run\n",
            "from myapp.core.engine import run\n",
            "from numpy.core import _multiarray\n",
            "from ._engine import run\n",
            "from myapp.core import __version__\n",
        ],
        ids=[
            "public_surface",
            "public_submodule",
            "third_party_internal",
            "relative_import",
            "dunder_name",
        ],
    )
    def test_PublicOrForeignImport_NoViolation(
        self, tmp_path: Path, source: str
    ) -> None:
        target = _write(tmp_path, "src/myapp/api/views.py", source)
        assert list(check_private_import(target, source)) == []

    def test_ImportFromWithinOwningPackage_NoViolation(self, tmp_path: Path) -> None:
        source = "from myapp.core._engine import run\n"
        target = _write(tmp_path, "src/myapp/core/service.py", source)
        assert list(check_private_import(target, source)) == []

    def test_PackageInitReexportsOwnInternal_NoViolation(self, tmp_path: Path) -> None:
        source = "from myapp.core._engine import run\n"
        target = _write(tmp_path, "src/myapp/core/__init__.py", source)
        assert list(check_private_import(target, source)) == []

    def test_TestModuleReachingInternal_NoViolation(self, tmp_path: Path) -> None:
        source = "from myapp.core._engine import run\n"
        target = _write(tmp_path, "tests/test_service.py", source)
        assert list(check_private_import(target, source)) == []

    @pytest.mark.parametrize(
        "source",
        [
            "from myapp.core._engine import run\n",
            "import myapp.core._engine\n",
            "from myapp.core.engine import _run\n",
            "from myapp.rules._shared import parse\n",
        ],
        ids=[
            "private_module_from",
            "private_module_import",
            "private_name_from_public_module",
            "sibling_package_internal",
        ],
    )
    def test_ReachIntoAnotherPackageInternal_FlagsViolation(
        self, tmp_path: Path, source: str
    ) -> None:
        target = _write(tmp_path, "src/myapp/api/views.py", source)
        violations = list(check_private_import(target, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_PRIVATE_IMPORT
        assert violations[0].line == 1

    def test_TopLevelModuleReachingSubpackageInternal_FlagsViolation(
        self, tmp_path: Path
    ) -> None:
        source = "from myapp.rules._shared import find_pyproject\n"
        target = _write(tmp_path, "src/myapp/runner.py", source)
        violations = list(check_private_import(target, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_PRIVATE_IMPORT


def _write(tmp_path: Path, relative: str, source: str) -> Path:
    """Writes `source` at `relative`, seeding `__init__.py` up its packages.

    Every directory between the `src` root and the file becomes a package so
    the rule can resolve the file's dotted module name.
    """
    parts = Path(relative).parts
    if parts[0] == "src":
        package = tmp_path / parts[0]
        for part in parts[1:-1]:
            package = package / part
            package.mkdir(parents=True, exist_ok=True)
            init = package / "__init__.py"
            if not init.exists():
                init.write_text("", encoding="utf-8")
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")
    return target
