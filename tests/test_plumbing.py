from pathlib import Path

import pytest

from repostyle.rules import (
    RS_FORWARDED_COLLABORATOR,
    RS_PARALLEL_CONSTRUCTION,
    check_forwarded_collaborator,
    check_parallel_construction,
)
from repostyle.runner import lint_package

_QUESTIONS = """\
from typing import Protocol


class AnswerCache(Protocol):
    def get(self, key: str) -> str: ...


class Questions:
    def __init__(self, *, workers: int = 8, backoff: float = 1.0) -> None:
        self.workers = workers
        self.backoff = backoff

    def ask(self) -> int:
        return self.workers
"""

_PORT_QUESTIONS = """\
from typing import Protocol


class AnswerCache(Protocol):
    def get(self, key: str) -> str: ...


class CachedQuestions:
    def __init__(self, answers: AnswerCache) -> None:
        self.answers = answers
"""

_FORWARDING_JUDGE = """\
from pkg.application.questions import Questions


class Judge:
    def __init__(self, workers: int = 8, backoff: float = 1.0) -> None:
        self._workers = workers
        self._backoff = backoff

    def check(self) -> int:
        return Questions(workers=self._workers, backoff=self._backoff).ask()
"""


class TestCheckForwardedCollaborator:
    @pytest.mark.parametrize(
        "judge",
        [
            _FORWARDING_JUDGE,
            "from pkg.application.questions import Questions\n\n\n"
            "class Judge:\n"
            "    def __init__(self, workers: int, backoff: float) -> None:\n"
            "        self._questions = Questions(workers=workers, backoff=backoff)\n",
            "from pkg.application.questions import Questions\n\n\n"
            "class Judge:\n"
            "    def __init__(self, workers: int, backoff: float) -> None:\n"
            "        self._questions = Questions(workers, backoff)\n",
            "from pkg.application import questions\n\n\n"
            "class Judge:\n"
            "    def __init__(self, workers: int, backoff: float) -> None:\n"
            "        self._questions = questions.Questions(workers, backoff)\n",
        ],
        ids=[
            "through-self-attribute",
            "keyword-in-init",
            "positional-in-init",
            "first-party-module-attribute",
        ],
    )
    def test_TwoParametersForwardedToOneClass_FlagsOwner(
        self, tmp_path: Path, judge: str
    ) -> None:
        files = _pkg(tmp_path, {"questions.py": _QUESTIONS, "judge.py": judge})
        findings = list(check_forwarded_collaborator(files))
        assert [(p.name, v.rule, v.line) for p, v in findings] == [
            ("judge.py", RS_FORWARDED_COLLABORATOR, 4)
        ]
        message = findings[0][1].message
        assert "'Judge' builds 'Questions'" in message
        assert "'workers', 'backoff'" in message
        assert "forwarding chain depth 1" in message
        assert "repostyle:structural-refactor" in message

    def test_ConstructorTakesPort_FlagsOwner(self, tmp_path: Path) -> None:
        judge = (
            "from pkg.application.questions import AnswerCache, CachedQuestions\n\n\n"
            "class Judge:\n"
            "    def __init__(self, answers: AnswerCache) -> None:\n"
            "        self._answers = answers\n\n"
            "    def check(self) -> None:\n"
            "        CachedQuestions(self._answers)\n"
        )
        files = _pkg(tmp_path, {"questions.py": _PORT_QUESTIONS, "judge.py": judge})
        (finding,) = check_forwarded_collaborator(files)
        assert finding[1].rule == RS_FORWARDED_COLLABORATOR
        assert "in 'check'" in finding[1].message
        assert "takes the port 'AnswerCache'" in finding[1].message

    def test_ForwardedThroughTwoClasses_ReportsChainDepth(self, tmp_path: Path) -> None:
        runner = (
            "from pkg.application.judge import Judge\n\n\n"
            "class Runner:\n"
            "    def __init__(self, workers: int, backoff: float) -> None:\n"
            "        self._judge = Judge(workers=workers, backoff=backoff)\n"
        )
        files = _pkg(
            tmp_path,
            {
                "questions.py": _QUESTIONS,
                "judge.py": _FORWARDING_JUDGE,
                "runner.py": runner,
            },
        )
        messages = {p.name: v.message for p, v in check_forwarded_collaborator(files)}
        assert "forwarding chain depth 2" in messages["runner.py"]

    def test_ForwardingCycle_Terminates(self, tmp_path: Path) -> None:
        cycle = (
            "from pkg.application.{other} import {target}\n\n\n"
            "class {name}:\n"
            "    def __init__(self, workers: int, backoff: float) -> None:\n"
            "        self._workers = workers\n"
            "        self._backoff = backoff\n\n"
            "    def build(self) -> object:\n"
            "        return {target}(workers=self._workers, backoff=self._backoff)\n"
        )
        files = _pkg(
            tmp_path,
            {
                "first.py": cycle.format(other="second", target="Second", name="First"),
                "second.py": cycle.format(other="first", target="First", name="Second"),
            },
        )
        findings = sorted(p.name for p, _ in check_forwarded_collaborator(files))
        assert findings == ["first.py", "second.py"]

    @pytest.mark.parametrize(
        ("modules", "pyproject"),
        [
            (
                {
                    "budget.py": "class CostBudget:\n"
                    "    def __init__(self, ceiling: float) -> None:\n"
                    "        self.ceiling = ceiling\n",
                    "judge.py": "from pkg.application.budget import CostBudget\n\n\n"
                    "class Judge:\n"
                    "    def __init__(self, ceiling: float) -> None:\n"
                    "        self._budget = CostBudget(ceiling)\n",
                },
                "",
            ),
            (
                {
                    "questions.py": _QUESTIONS,
                    "judge.py": _FORWARDING_JUDGE.replace(
                        "return Questions",
                        "print(self._workers)\n        return Questions",
                    ),
                },
                "",
            ),
            (
                {
                    "questions.py": _QUESTIONS,
                    "judge.py": _FORWARDING_JUDGE,
                    "other.py": "class Questions:\n    pass\n",
                },
                "",
            ),
            (
                {
                    "judge.py": _QUESTIONS
                    + "\n\n"
                    + _FORWARDING_JUDGE.split("\n", 3)[3],
                },
                "",
            ),
            (
                {
                    "questions.py": _QUESTIONS,
                    "judge.py": "import dataclasses\n\n"
                    "from pkg.application.questions import Questions\n\n\n"
                    "@dataclasses.dataclass\n"
                    "class Judge:\n"
                    "    workers: int\n"
                    "    backoff: float\n\n"
                    "    def check(self) -> int:\n"
                    "        return Questions(\n"
                    "            workers=self.workers, backoff=self.backoff\n"
                    "        ).ask()\n",
                },
                "",
            ),
            (
                {
                    "questions.py": _QUESTIONS,
                    "judge.py": _FORWARDING_JUDGE.replace(
                        "from pkg.application.questions", "from vendor.questions"
                    ),
                },
                "",
            ),
            (
                {"questions.py": _QUESTIONS, "judge.py": _FORWARDING_JUDGE},
                '[tool.repostyle]\ncollaborator-layer-globs = ["*/domain/**"]\n',
            ),
            (
                {
                    "questions.py": _QUESTIONS,
                    "judge.py": _FORWARDING_JUDGE.replace(
                        "from pkg.application.questions import Questions",
                        "from vendor import sdk",
                    ).replace("return Questions(", "return sdk.Questions("),
                },
                "",
            ),
            (
                {
                    "questions.py": _QUESTIONS,
                    "judge.py": "try:\n    from vendor import Questions\n"
                    "except ImportError:\n    Questions = None\n\n\n"
                    + _FORWARDING_JUDGE.split("\n", 3)[3],
                },
                "",
            ),
            (
                {
                    "errors.py": "class TimeoutError(Exception):\n"
                    "    def __init__(self, operation: str, seconds: float) -> None:\n"
                    "        super().__init__(operation, seconds)\n",
                    "judge.py": "class Judge:\n"
                    "    def __init__(self, operation: str, seconds: float) -> None:\n"
                    "        self._operation = operation\n"
                    "        self._seconds = seconds\n\n"
                    "    def check(self) -> None:\n"
                    "        raise TimeoutError(self._operation, self._seconds)\n",
                },
                "",
            ),
            (
                {
                    "questions.py": _QUESTIONS,
                    "judge.py": "from pkg.application.questions import Questions\n\n\n"
                    "class Judge:\n"
                    "    def __init__(self, workers: int, backoff: float) -> None:\n"
                    "        self._make = lambda workers, backoff: Questions(\n"
                    "            workers=workers, backoff=backoff\n"
                    "        )\n",
                },
                "",
            ),
            (
                {
                    "questions.py": _QUESTIONS,
                    "judge.py": _FORWARDING_JUDGE.replace("self._", "self."),
                },
                "",
            ),
        ],
        ids=[
            "single-wrapped-value",
            "parameter-also-used-locally",
            "ambiguous-callee-name",
            "same-module-collaborator",
            "dataclass-record-fields",
            "third-party-import-of-same-name",
            "outside-configured-layers",
            "third-party-module-attribute",
            "guarded-third-party-import",
            "builtin-named-exception",
            "lambda-shadows-parameter",
            "public-attribute",
        ],
    )
    def test_NotPlumbing_NoViolation(
        self, tmp_path: Path, modules: dict[str, str], pyproject: str
    ) -> None:
        files = _pkg(tmp_path, modules, pyproject=pyproject)
        assert list(check_forwarded_collaborator(files)) == []

    def test_WiringModuleOutsideLayers_NoViolation(self, tmp_path: Path) -> None:
        files = _pkg(tmp_path, {"questions.py": _QUESTIONS})
        command = tmp_path / "src" / "pkg" / "ingest_command.py"
        source = _FORWARDING_JUDGE
        command.write_text(source, encoding="utf-8")
        assert list(check_forwarded_collaborator([*files, (command, source)])) == []


_SETTINGS = """\
class Settings:
    def __init__(self, **values: object) -> None:
        self.values = values
"""


def _build(pairs: int, name: str = "Settings") -> str:
    """Returns a module constructing `name` from `pairs` keyword arguments."""
    keywords = "".join(f"    k{i}=arguments.k{i},\n" for i in range(pairs))
    return (
        f"from pkg.settings import {name}\n\n\n"
        f"def build(arguments):\n    return {name}(\n{keywords}    )\n"
    )


class TestCheckParallelConstruction:
    def test_SamePairsInTwoModules_FlagsBothCalls(self, tmp_path: Path) -> None:
        files = _pkg(
            tmp_path,
            {
                "settings.py": _SETTINGS,
                "ingest.py": _build(8),
                "bootstrap.py": _build(9),
            },
            package="pkg",
        )
        findings = sorted(
            (p.name, v.rule, v.line) for p, v in check_parallel_construction(files)
        )
        assert findings == [
            ("bootstrap.py", RS_PARALLEL_CONSTRUCTION, 5),
            ("ingest.py", RS_PARALLEL_CONSTRUCTION, 5),
        ]

    def test_SamePairs_MessageNamesOtherSite(self, tmp_path: Path) -> None:
        files = _pkg(
            tmp_path,
            {
                "settings.py": _SETTINGS,
                "ingest.py": _build(8),
                "bootstrap.py": _build(8),
            },
            package="pkg",
        )
        messages = {p.name: v.message for p, v in check_parallel_construction(files)}
        assert "src/pkg/bootstrap.py:5" in messages["ingest.py"]
        assert "same 8 keyword=value pairs" in messages["ingest.py"]

    @pytest.mark.parametrize(
        ("modules", "pyproject"),
        [
            ({"ingest.py": _build(7), "bootstrap.py": _build(7)}, ""),
            ({"ingest.py": _build(8) + "\n\n" + _build(8).split("\n", 3)[3]}, ""),
            ({"ingest.py": _build(8), "test_ingest.py": _build(8)}, ""),
            (
                {"ingest.py": _build(8), "bootstrap.py": _build(8)},
                "[tool.repostyle]\nparallel-construction-min-pairs = 9\n",
            ),
        ],
        ids=["below-threshold", "same-module", "test-module", "configured-threshold"],
    )
    def test_NotParallel_NoViolation(
        self, tmp_path: Path, modules: dict[str, str], pyproject: str
    ) -> None:
        files = _pkg(
            tmp_path, {"settings.py": _SETTINGS, **modules}, pyproject, package="pkg"
        )
        assert list(check_parallel_construction(files)) == []

    def test_FindingsScopedToPassedPaths_ReportsOnlyThose(self, tmp_path: Path) -> None:
        files = _pkg(
            tmp_path,
            {
                "settings.py": _SETTINGS,
                "ingest.py": _build(8),
                "bootstrap.py": _build(8),
            },
            package="pkg",
        )
        ingest = next(path for path, _ in files if path.name == "ingest.py")
        findings = lint_package([ingest], {RS_PARALLEL_CONSTRUCTION})
        assert [path.name for path in findings] == ["ingest.py"]


def _pkg(
    tmp_path: Path,
    modules: dict[str, str],
    pyproject: str = "",
    package: str = "pkg/application",
) -> list[tuple[Path, str]]:
    """Writes `modules` into a package under `tmp_path/src`, returning them."""
    (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    directory = tmp_path / "src" / package
    directory.mkdir(parents=True)
    for parent in [directory, *directory.parents]:
        if parent == tmp_path / "src":
            break
        (parent / "__init__.py").write_text("", encoding="utf-8")
    files: list[tuple[Path, str]] = []
    for name, source in modules.items():
        path = directory / name
        path.write_text(source, encoding="utf-8")
        files.append((path, source))
    return files
