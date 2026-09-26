from pathlib import Path

import pytest

from repostyle._shared import (
    _gitignore_prunes_dir,
    _GitignoreRules,
    _parse_gitignore,
)
from repostyle.rules import (
    RS_SHOULD_BE_PRIVATE,
)
from repostyle.runner import (
    _package_files,
    expand_paths,
    lint_package,
)

_UNDERWRAPPED_DOCSTRING = 'def f():\n    """Summary.\n\n    aaa\n    bbb\n    """\n'

_ACRONYM_AND_SUFFIX_SOURCE = "class FhirManager: ...\n"


class TestExpandPaths:
    def test_Directory_ExpandsToLintableFilesSorted(self, tmp_path: Path) -> None:
        (tmp_path / "b.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "notes.txt").write_text("x\n", encoding="utf-8")
        assert expand_paths([tmp_path]) == [tmp_path / "a.py", tmp_path / "b.py"]

    def test_Directory_RecursesIntoSubdirectories(self, tmp_path: Path) -> None:
        nested = tmp_path / "pkg"
        nested.mkdir()
        target = nested / "x.py"
        target.write_text("x = 1\n", encoding="utf-8")
        assert expand_paths([tmp_path]) == [target]

    def test_Directory_SkipsCacheAndBuildDirectories(self, tmp_path: Path) -> None:
        for skipped in (".git", ".venv", ".mypy_cache", "build", "__pycache__"):
            hidden = tmp_path / skipped
            hidden.mkdir()
            (hidden / "x.py").write_text("x = 1\n", encoding="utf-8")
        assert expand_paths([tmp_path]) == []

    @pytest.mark.parametrize(
        "directory", [".github/workflows", ".claude"], ids=["github", "claude"]
    )
    def test_UnprunedDotDirectory_IsWalked(
        self, tmp_path: Path, directory: str
    ) -> None:
        nested = tmp_path / directory
        nested.mkdir(parents=True)
        target = nested / "x.yaml"
        target.write_text("k: v\n", encoding="utf-8")
        assert expand_paths([tmp_path]) == [target]

    def test_DotPrefixedFile_IsWalked(self, tmp_path: Path) -> None:
        config = tmp_path / ".pre-commit-config.yaml"
        config.write_text("k: v\n", encoding="utf-8")
        app = tmp_path / "app.py"
        app.write_text("x = 1\n", encoding="utf-8")
        assert expand_paths([tmp_path]) == [config, app]

    def test_File_PassesThroughRegardlessOfSuffix(self, tmp_path: Path) -> None:
        target = tmp_path / "notes.txt"
        target.write_text("x\n", encoding="utf-8")
        assert expand_paths([target]) == [target]

    @pytest.mark.parametrize(
        "second_arg", ["file", "nested_dir"], ids=["file", "nested_dir"]
    )
    def test_OverlappingArgument_DropsTheDuplicate(
        self, tmp_path: Path, second_arg: str
    ) -> None:
        nested = tmp_path / "pkg"
        nested.mkdir()
        target = nested / "x.py"
        target.write_text("x = 1\n", encoding="utf-8")
        second = target if second_arg == "file" else nested
        assert expand_paths([tmp_path, second]) == [target]

    @pytest.mark.parametrize(
        ("globs", "dropped", "kept"),
        [
            ('["*_grpc/*.py"]', ["pkg/_grpc/stub.py"], ["pkg/app.py"]),
            (
                '["vendor/*", "*_pb2.py"]',
                ["vendor/lib.py", "service_pb2.py"],
                ["app.py"],
            ),
        ],
        ids=["single_glob", "multiple_globs"],
    )
    def test_ExcludeGlobs_DropsMatchingFiles(
        self, tmp_path: Path, globs: str, dropped: list[str], kept: list[str]
    ) -> None:
        _write_exclude_config(tmp_path, globs)
        for relative in [*dropped, *kept]:
            target = tmp_path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("x = 1\n", encoding="utf-8")
        expanded = expand_paths([tmp_path])
        assert {tmp_path / relative for relative in dropped}.isdisjoint(expanded)
        assert {tmp_path / relative for relative in kept} <= set(expanded)

    def test_ExcludedFilePassedExplicitly_DropsFromScan(self, tmp_path: Path) -> None:
        _write_exclude_config(tmp_path, '["_grpc/*.py"]')
        generated = tmp_path / "_grpc"
        generated.mkdir()
        stub = generated / "stub.py"
        stub.write_text("x = 1\n", encoding="utf-8")
        assert expand_paths([stub]) == []


class TestLintPackage:
    def test_RootPathsOverride_ScansTheOriginalArgumentsTree(
        self, tmp_path: Path
    ) -> None:
        """Passing `root_paths` widens the scan to the real package root.

        Without it the scan misses the call to `helper` in `outer.py` and
        misreports it as should-be-private; with it the finding disappears.
        """
        nested = tmp_path / "aaa_sub"
        nested.mkdir()
        target = nested / "mod.py"
        target.write_text(
            '__all__ = ["run"]\n\n\ndef helper():\n    return 1\n\n\n'
            "def run():\n    return helper()\n",
            encoding="utf-8",
        )
        (tmp_path / "outer.py").write_text(
            "def go():\n    return helper()\n", encoding="utf-8"
        )
        expanded = [target]
        narrow = lint_package(expanded, {RS_SHOULD_BE_PRIVATE})
        broad = lint_package(expanded, {RS_SHOULD_BE_PRIVATE}, root_paths=[tmp_path])
        assert target.resolve() in narrow
        assert broad == {}

    def test_ExcludedFileReference_KeepsNamePublic(self, tmp_path: Path) -> None:
        """A reference from an excluded file keeps a name off RS029.

        `helper` is used only from an `exclude`-silenced `_grpc` stub, so
        dropping that stub from the cross-module index would misreport it as
        should-be-private. The index reads the excluded file, so the reference
        counts and the name is left public.
        """
        _write_exclude_config(tmp_path, '["_grpc/*.py"]')
        target = tmp_path / "app.py"
        target.write_text(
            '__all__ = ["run"]\n\n\ndef helper():\n    return 1\n\n\n'
            "def run():\n    return helper()\n",
            encoding="utf-8",
        )
        generated = tmp_path / "_grpc"
        generated.mkdir()
        (generated / "stub.py").write_text(
            "def go():\n    return helper()\n", encoding="utf-8"
        )
        findings = lint_package([target], {RS_SHOULD_BE_PRIVATE}, root_paths=[tmp_path])
        assert findings == {}


class TestPackageWalkPruning:
    """The whole-package index prunes vendored trees but not excluded files.

    Reading and tokenizing every file under a working-tree virtualenv was what
    made a run go CPU-bound for minutes in a venv-heavy repo, so a `venv`
    subtree must never be descended. An `exclude` glob, by contrast, silences a
    file's findings without removing it from the cross-module index, so RS029
    still counts a reference from excluded generated code.
    """

    def test_VenvDirectory_PrunedFromPackageIndex(self, tmp_path: Path) -> None:
        """A working-tree `venv/` is pruned by the structural skip alone."""
        (tmp_path / "pyproject.toml").write_text("[tool.repostyle]\n", encoding="utf-8")
        vendored = tmp_path / "venv" / "lib"
        vendored.mkdir(parents=True)
        (vendored / "dep.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "app.py").write_text("y = 2\n", encoding="utf-8")
        read = {path.resolve() for path, _ in _package_files(tmp_path)}
        assert read == {(tmp_path / "app.py").resolve()}

    def test_ExcludedFile_StillReadIntoPackageIndex(self, tmp_path: Path) -> None:
        """An `exclude` glob keeps a file in the package index (RS029)."""
        _write_exclude_config(tmp_path, '["_grpc/*.py"]')
        generated = tmp_path / "_grpc"
        generated.mkdir()
        (generated / "stub.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "app.py").write_text("y = 2\n", encoding="utf-8")
        read = {path.resolve() for path, _ in _package_files(tmp_path)}
        assert read == {
            (tmp_path / "app.py").resolve(),
            (generated / "stub.py").resolve(),
        }


class TestNestedCheckoutPruning:
    """A directory holding its own `.git` is another repo, so it is pruned.

    A `git worktree` parked under `.claude/` is a whole second copy of the
    repo. Reading it dominates the package scan, and it silences RS029: the
    copy of a module counts as a second module referencing every name the
    original defines. A subproject with no `.git` of its own is part of this
    repo and stays in the index.
    """

    def test_LinkedWorktree_PrunedFromPackageIndex(self, tmp_path: Path) -> None:
        """A worktree's `.git` file marks the tree as a separate checkout."""
        (tmp_path / "pyproject.toml").write_text("[tool.repostyle]\n", encoding="utf-8")
        worktree = tmp_path / ".claude" / "worktrees" / "wt"
        worktree.mkdir(parents=True)
        (worktree / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
        (worktree / "copy.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "app.py").write_text("y = 2\n", encoding="utf-8")
        read = {path.resolve() for path, _ in _package_files(tmp_path)}
        assert read == {(tmp_path / "app.py").resolve()}

    def test_ClonedRepository_PrunedFromPackageIndex(self, tmp_path: Path) -> None:
        """A clone's `.git` directory marks the tree the same way."""
        (tmp_path / "pyproject.toml").write_text("[tool.repostyle]\n", encoding="utf-8")
        clone = tmp_path / "vendor" / "dep"
        (clone / ".git").mkdir(parents=True)
        (clone / "dep.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "app.py").write_text("y = 2\n", encoding="utf-8")
        read = {path.resolve() for path, _ in _package_files(tmp_path)}
        assert read == {(tmp_path / "app.py").resolve()}

    def test_NestedCheckout_DroppedFromDirectoryExpansion(self, tmp_path: Path) -> None:
        """The same prune applies when a directory argument is expanded."""
        worktree = tmp_path / "wt"
        worktree.mkdir()
        (worktree / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
        (worktree / "copy.py").write_text("x = 1\n", encoding="utf-8")
        target = tmp_path / "app.py"
        target.write_text("y = 2\n", encoding="utf-8")
        assert expand_paths([tmp_path]) == [target]

    def test_SubprojectWithoutGit_StaysInPackageIndex(self, tmp_path: Path) -> None:
        """A monorepo subproject is part of this repo, so it is still read.

        Its own `pyproject.toml` does not make it a separate checkout, and
        pruning on that file instead would drop a real cross-module reference.
        """
        (tmp_path / "pyproject.toml").write_text("[tool.repostyle]\n", encoding="utf-8")
        subproject = tmp_path / "packages" / "sub"
        subproject.mkdir(parents=True)
        (subproject / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
        (subproject / "mod.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "app.py").write_text("y = 2\n", encoding="utf-8")
        read = {path.resolve() for path, _ in _package_files(tmp_path)}
        assert read == {
            (tmp_path / "app.py").resolve(),
            (subproject / "mod.py").resolve(),
        }

    def test_WalkRoot_NeverPrunedByItsOwnGit(self, tmp_path: Path) -> None:
        """A run from inside a checkout walks it, since only children prune."""
        (tmp_path / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
        (tmp_path / "pyproject.toml").write_text("[tool.repostyle]\n", encoding="utf-8")
        (tmp_path / "app.py").write_text("y = 2\n", encoding="utf-8")
        read = {path.resolve() for path, _ in _package_files(tmp_path)}
        assert read == {(tmp_path / "app.py").resolve()}

    def test_WorktreeCopyOfAModule_NoLongerMasksTheFinding(
        self, tmp_path: Path
    ) -> None:
        """A stale worktree copy stops counting as a cross-module reference.

        `helper` is used only inside `app.py`, so RS029 fires. A byte-identical
        copy under a worktree would otherwise register as another module using
        the name and silence the rule.
        """
        (tmp_path / "pyproject.toml").write_text("[tool.repostyle]\n", encoding="utf-8")
        source = (
            '__all__ = ["run"]\n\n\ndef helper():\n    return 1\n\n\n'
            "def run():\n    return helper()\n"
        )
        target = tmp_path / "app.py"
        target.write_text(source, encoding="utf-8")
        worktree = tmp_path / ".claude" / "worktrees" / "wt"
        worktree.mkdir(parents=True)
        (worktree / ".git").write_text("gitdir: /elsewhere\n", encoding="utf-8")
        (worktree / "app.py").write_text(source, encoding="utf-8")
        findings = lint_package([target], {RS_SHOULD_BE_PRIVATE}, root_paths=[tmp_path])
        assert [v.line for v in findings[target.resolve()]] == [4]


class TestParseGitignore:
    """Parsing a repo's `.gitignore` into repostyle's pruning rules."""

    def test_DirectoryPatterns_SplitIntoAnchoredAndBare(self, tmp_path: Path) -> None:
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text(
            "/build\nvenv/\nsrc/generated\nnode_modules\n", encoding="utf-8"
        )
        assert _parse_gitignore(gitignore) == _GitignoreRules(
            anchored=("build", "src/generated"),
            bare=("venv", "node_modules"),
            negated_prefixes=(),
            is_disabled=False,
        )

    def test_BlankAndCommentLines_AreIgnored(self, tmp_path: Path) -> None:
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("# a comment\n\n   \nvenv/\n", encoding="utf-8")
        assert _parse_gitignore(gitignore).bare == ("venv",)

    def test_AnchoredNegation_RecordsGuardedPrefix(self, tmp_path: Path) -> None:
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("build/\n!build/keep\n", encoding="utf-8")
        rules = _parse_gitignore(gitignore)
        assert rules.negated_prefixes == ("build/keep",)
        assert not rules.is_disabled

    def test_UnanchoredNegation_DisablesPruning(self, tmp_path: Path) -> None:
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("build/\n!keep\n", encoding="utf-8")
        assert _parse_gitignore(gitignore).is_disabled

    def test_AbsentFile_ParsesToEmptyRules(self, tmp_path: Path) -> None:
        empty = _GitignoreRules((), (), (), is_disabled=False)
        assert _parse_gitignore(None) == empty
        assert _parse_gitignore(tmp_path / "absent") == empty


class TestGitignorePrunesDir:
    """Matching a directory against the parsed `.gitignore` rules."""

    def test_BareName_PrunesAtAnyDepth(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        rules = _GitignoreRules((), ("venv",), (), is_disabled=False)
        assert _gitignore_prunes_dir(tmp_path / "venv", pyproject, rules)
        assert _gitignore_prunes_dir(tmp_path / "src" / "venv", pyproject, rules)
        assert not _gitignore_prunes_dir(tmp_path / "src", pyproject, rules)

    def test_AnchoredName_PrunesOnlyAtRoot(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        rules = _GitignoreRules(("build",), (), (), is_disabled=False)
        assert _gitignore_prunes_dir(tmp_path / "build", pyproject, rules)
        assert not _gitignore_prunes_dir(tmp_path / "sub" / "build", pyproject, rules)

    def test_NegatedSubtree_SparesEnclosingDirectory(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        rules = _GitignoreRules((), ("build",), ("build/keep",), is_disabled=False)
        assert not _gitignore_prunes_dir(tmp_path / "build", pyproject, rules)

    def test_Disabled_PrunesNothing(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        rules = _GitignoreRules((), ("venv",), (), is_disabled=True)
        assert not _gitignore_prunes_dir(tmp_path / "venv", pyproject, rules)

    def test_NoPatterns_PrunesNothing(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        rules = _GitignoreRules((), (), (), is_disabled=False)
        assert not _gitignore_prunes_dir(tmp_path / "venv", pyproject, rules)


class TestWalkGitignorePruning:
    """Honoring `.gitignore` prunes a tree from every walk when opted in.

    A gitignored path is treated as outside the repo entirely, so it is pruned
    from both the findings walk and the whole-package index, unlike `exclude`,
    which keeps a file readable by the cross-module index. The flag is off by
    default, so a repo that has not opted in walks a gitignored tree unchanged.
    """

    def test_RespectGitignore_PrunesTreeFromExpansion(self, tmp_path: Path) -> None:
        _write_gitignore_repo(tmp_path, should_respect=True, gitignore="vendored/\n")
        (tmp_path / "vendored").mkdir()
        (tmp_path / "vendored" / "dep.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "app.py").write_text("y = 2\n", encoding="utf-8")
        expanded = expand_paths([tmp_path])
        assert tmp_path / "vendored" / "dep.py" not in expanded
        assert tmp_path / "app.py" in expanded

    def test_FlagOff_WalksGitignoredTree(self, tmp_path: Path) -> None:
        _write_gitignore_repo(tmp_path, should_respect=False, gitignore="vendored/\n")
        (tmp_path / "vendored").mkdir()
        (tmp_path / "vendored" / "dep.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "app.py").write_text("y = 2\n", encoding="utf-8")
        assert tmp_path / "vendored" / "dep.py" in expand_paths([tmp_path])

    def test_RespectGitignore_HidesTreeFromPackageIndex(self, tmp_path: Path) -> None:
        _write_gitignore_repo(tmp_path, should_respect=True, gitignore="_generated/\n")
        (tmp_path / "_generated").mkdir()
        (tmp_path / "_generated" / "stub.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "app.py").write_text("y = 2\n", encoding="utf-8")
        read = {path.resolve() for path, _ in _package_files(tmp_path)}
        assert read == {(tmp_path / "app.py").resolve()}

    def test_GitignoredFileReference_DropsNameFromIndex(self, tmp_path: Path) -> None:
        """A reference from a gitignored file no longer keeps a name public.

        Unlike `exclude`, `respect-gitignore` makes the referencing `_grpc`
        stub invisible to the cross-module index, so `helper` reads as used
        only within its own module and RS029 flags it should-be-private. This
        is the clean split from the exclude case, which keeps `helper` public.
        """
        _write_gitignore_repo(tmp_path, should_respect=True, gitignore="_grpc/\n")
        target = tmp_path / "app.py"
        target.write_text(
            '__all__ = ["run"]\n\n\ndef helper():\n    return 1\n\n\n'
            "def run():\n    return helper()\n",
            encoding="utf-8",
        )
        generated = tmp_path / "_grpc"
        generated.mkdir()
        (generated / "stub.py").write_text(
            "def go():\n    return helper()\n", encoding="utf-8"
        )
        findings = lint_package([target], {RS_SHOULD_BE_PRIVATE}, root_paths=[tmp_path])
        assert target.resolve() in findings


def _write_exclude_config(tmp_path: Path, exclude: str) -> None:
    (tmp_path / "pyproject.toml").write_text(
        f"[tool.repostyle]\nexclude = {exclude}\n", encoding="utf-8"
    )


def _write_gitignore_repo(
    tmp_path: Path, *, should_respect: bool, gitignore: str
) -> None:
    flag = "\nrespect-gitignore = true" if should_respect else ""
    (tmp_path / "pyproject.toml").write_text(
        f"[tool.repostyle]{flag}\n", encoding="utf-8"
    )
    (tmp_path / ".gitignore").write_text(gitignore, encoding="utf-8")
