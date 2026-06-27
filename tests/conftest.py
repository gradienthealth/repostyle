import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Return a path to a freshly initialized, committable git repo"""
    for args in (
        ["init"],
        ["config", "user.email", "test@example.com"],
        ["config", "user.name", "Test"],
    ):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)
    return tmp_path


@pytest.fixture
def git(git_repo: Path) -> Callable[..., None]:
    """Return a callable running a git subcommand inside `git_repo`"""

    def run(*args: str) -> None:
        subprocess.run(["git", *args], cwd=git_repo, check=True, capture_output=True)

    return run
