import subprocess
from collections.abc import Callable
from pathlib import Path

from repostyle.changed_lines import changed_lines, resolve_diff_base


class TestChangedLines:
    def test_ModifiedLine_ReportsThatLine(
        self, git_repo: Path, git: Callable[..., None]
    ) -> None:
        target = git_repo / "m.py"
        target.write_text("a = 1\nb = 2\nc = 3\n", encoding="utf-8")
        git("add", "m.py")
        git("commit", "-m", "base")
        target.write_text("a = 1\nb = 22\nc = 3\n", encoding="utf-8")
        assert changed_lines(target, "HEAD") == {2}

    def test_AddedLines_ReportsEachNewLine(
        self, git_repo: Path, git: Callable[..., None]
    ) -> None:
        target = git_repo / "m.py"
        target.write_text("a = 1\n", encoding="utf-8")
        git("add", "m.py")
        git("commit", "-m", "base")
        target.write_text("a = 1\nb = 2\nc = 3\n", encoding="utf-8")
        assert changed_lines(target, "HEAD") == {2, 3}

    def test_UnchangedTrackedFile_ReturnsEmptySet(
        self, git_repo: Path, git: Callable[..., None]
    ) -> None:
        target = git_repo / "m.py"
        target.write_text("a = 1\n", encoding="utf-8")
        git("add", "m.py")
        git("commit", "-m", "base")
        assert changed_lines(target, "HEAD") == set()

    def test_UntrackedFile_ReturnsNone(
        self, git_repo: Path, git: Callable[..., None]
    ) -> None:
        (git_repo / "tracked.py").write_text("a = 1\n", encoding="utf-8")
        git("add", "tracked.py")
        git("commit", "-m", "base")
        untracked = git_repo / "new.py"
        untracked.write_text("a = 1\n", encoding="utf-8")
        assert changed_lines(untracked, "HEAD") is None

    def test_UnknownBase_ReturnsNone(
        self, git_repo: Path, git: Callable[..., None]
    ) -> None:
        target = git_repo / "m.py"
        target.write_text("a = 1\n", encoding="utf-8")
        git("add", "m.py")
        git("commit", "-m", "base")
        assert changed_lines(target, "no-such-ref") is None


class TestResolveDiffBase:
    def test_KnownRef_IsReturnedUnchanged(
        self, git_repo: Path, git: Callable[..., None]
    ) -> None:
        (git_repo / "m.py").write_text("a = 1\n", encoding="utf-8")
        git("add", "m.py")
        git("commit", "-m", "base")
        assert resolve_diff_base(git_repo, "HEAD") == "HEAD"

    def test_UnknownRef_ReturnsNone(
        self, git_repo: Path, git: Callable[..., None]
    ) -> None:
        (git_repo / "m.py").write_text("a = 1\n", encoding="utf-8")
        git("add", "m.py")
        git("commit", "-m", "base")
        assert resolve_diff_base(git_repo, "no-such-ref") is None

    def test_NoRefRequested_ResolvesTheDefaultBranchMergeBase(
        self, git_repo: Path, git: Callable[..., None]
    ) -> None:
        (git_repo / "m.py").write_text("a = 1\n", encoding="utf-8")
        git("add", "m.py")
        git("commit", "-m", "base")
        git("branch", "-M", "main")
        git("checkout", "-b", "feature")
        (git_repo / "m.py").write_text("a = 2\n", encoding="utf-8")
        git("commit", "-am", "change")
        head_of_main = _rev("main", git_repo)
        assert resolve_diff_base(git_repo, None) == head_of_main

    def test_NoDefaultBranch_ReturnsNone(self, tmp_path: Path) -> None:
        assert resolve_diff_base(tmp_path, None) is None


def _rev(ref: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", ref], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()
