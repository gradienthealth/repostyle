from collections.abc import Callable
from pathlib import Path

from pystyle.changed_lines import changed_lines


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
