from pathlib import Path

from repostyle.rules import RS_SHOULD_BE_PRIVATE, check_should_be_private
from repostyle.runner import lint_package

# A module whose public `run` (exported) calls a public `helper` that no other
# module references: `helper` leaked public scope.
_LEAKED = """\
__all__ = ["run"]


def helper():
    return 1


def run():
    return helper()
"""


class TestCheckShouldBePrivate:
    def test_PublicNameUsedOnlyInOwnModule_FlagsViolation(self, tmp_path: Path) -> None:
        files = _pkg(tmp_path, {"mod.py": _LEAKED})
        violations = list(check_should_be_private(files))
        assert len(violations) == 1
        path, violation = violations[0]
        assert path.name == "mod.py"
        assert violation.rule == RS_SHOULD_BE_PRIVATE
        assert "helper" in violation.message

    def test_NameInDunderAll_NoViolation(self, tmp_path: Path) -> None:
        exported = _LEAKED.replace('["run"]', '["run", "helper"]')
        files = _pkg(tmp_path, {"mod.py": exported})
        assert list(check_should_be_private(files)) == []

    def test_NameImportedBySibling_NoViolation(self, tmp_path: Path) -> None:
        sibling = "from pkg.mod import helper\n\n\ndef go():\n    return helper()\n"
        files = _pkg(tmp_path, {"mod.py": _LEAKED, "other.py": sibling})
        assert list(check_should_be_private(files)) == []

    def test_NameAccessedAsAttributeInSibling_NoViolation(self, tmp_path: Path) -> None:
        sibling = "import pkg.mod\n\n\nx = pkg.mod.helper\n"
        files = _pkg(tmp_path, {"mod.py": _LEAKED, "other.py": sibling})
        assert list(check_should_be_private(files)) == []

    def test_NameReexportedFromPublicModule_NoViolation(self, tmp_path: Path) -> None:
        files = _pkg(
            tmp_path,
            {"mod.py": _LEAKED},
            pyproject='[tool.repostyle]\npublic-modules = ["src/pkg/mod.py"]\n',
        )
        assert list(check_should_be_private(files)) == []

    def test_UnderscorePrefixedName_NoViolation(self, tmp_path: Path) -> None:
        private = _LEAKED.replace("helper", "_helper")
        files = _pkg(tmp_path, {"mod.py": private})
        assert list(check_should_be_private(files)) == []

    def test_UnusedPublicName_NoViolation(self, tmp_path: Path) -> None:
        orphan = _LEAKED.replace("return helper()", "return 2")
        files = _pkg(tmp_path, {"mod.py": orphan})
        assert list(check_should_be_private(files)) == []

    def test_EntryPointFunction_NoViolation(self, tmp_path: Path) -> None:
        cli = "def main():\n    return 0\n\n\nif __name__ == '__main__':\n    main()\n"
        files = _pkg(
            tmp_path,
            {"cli.py": cli},
            pyproject='[project.scripts]\nmytool = "pkg.cli:main"\n',
        )
        assert list(check_should_be_private(files)) == []

    def test_NameInPublicNamesAllowlist_NoViolation(self, tmp_path: Path) -> None:
        files = _pkg(
            tmp_path,
            {"mod.py": _LEAKED},
            pyproject='[tool.repostyle]\npublic-names = ["helper"]\n',
        )
        assert list(check_should_be_private(files)) == []

    def test_NameCarryingPublicDecorator_NoViolation(self, tmp_path: Path) -> None:
        decorated = _LEAKED.replace("def helper():", "@fixture\ndef helper():")
        files = _pkg(
            tmp_path,
            {"mod.py": decorated},
            pyproject='[tool.repostyle]\npublic-decorators = ["fixture"]\n',
        )
        assert list(check_should_be_private(files)) == []


class TestLintPackage:
    def test_FindingsScopedToInvocationPaths(self, tmp_path: Path) -> None:
        files = _pkg(
            tmp_path,
            {
                "alpha.py": _LEAKED.replace("helper", "alpha_only"),
                "beta.py": _LEAKED.replace("helper", "beta_only"),
            },
        )
        alpha = next(path for path, _ in files if path.name == "alpha.py")
        findings = lint_package([alpha], {RS_SHOULD_BE_PRIVATE})
        assert set(findings) == {alpha.resolve()}
        assert findings[alpha.resolve()][0].rule == RS_SHOULD_BE_PRIVATE

    def test_PackageUnderDotDirectoryAncestor_StillScanned(
        self, tmp_path: Path
    ) -> None:
        root = tmp_path / ".worktrees" / "repo"
        root.mkdir(parents=True)
        files = _pkg(root, {"mod.py": _LEAKED})
        mod = next(path for path, _ in files if path.name == "mod.py")
        assert mod.resolve() in lint_package([mod], {RS_SHOULD_BE_PRIVATE})

    def test_SuppressionDirectiveDropsFinding(self, tmp_path: Path) -> None:
        suppressed = _LEAKED.replace(
            "def helper():", "def helper():  # style: ignore[RS029]"
        )
        files = _pkg(tmp_path, {"mod.py": suppressed})
        mod = next(path for path, _ in files if path.name == "mod.py")
        assert lint_package([mod], {RS_SHOULD_BE_PRIVATE}) == {}

    def test_RuleNotEnabled_NoWork(self, tmp_path: Path) -> None:
        files = _pkg(tmp_path, {"mod.py": _LEAKED})
        mod = next(path for path, _ in files if path.name == "mod.py")
        assert lint_package([mod], set()) == {}

    def test_RepostyleOwnSource_HasNoLeakedInternalName(self) -> None:
        # Dogfood RS029 over repostyle's own source the way the hook does,
        # pinning that no public symbol leaks internal-only scope.
        package = Path(__file__).resolve().parents[1] / "src" / "repostyle"
        sources = [
            path for path in package.rglob("*.py") if "__pycache__" not in path.parts
        ]
        assert package / "__init__.py" in sources
        assert lint_package(sources, {RS_SHOULD_BE_PRIVATE}) == {}


def _pkg(
    tmp_path: Path, modules: dict[str, str], pyproject: str = ""
) -> list[tuple[Path, str]]:
    """Writes a `pkg` package under `tmp_path/src` and returns its files."""
    (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    package = tmp_path / "src" / "pkg"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    files: list[tuple[Path, str]] = []
    for name, source in modules.items():
        path = package / name
        path.write_text(source, encoding="utf-8")
        files.append((path, source))
    return files
