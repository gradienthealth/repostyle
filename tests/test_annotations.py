import sys
from pathlib import Path

import pytest

from repostyle.rules import RS_DEEPLY_NESTED_TYPE, check_deeply_nested_type


class TestCheckDeeplyNestedType:
    @pytest.mark.parametrize(
        "source",
        [
            pytest.param(
                "def f(rows: list[tuple[str, list[int]]]) -> None: ...\n",
                id="parameter",
            ),
            pytest.param(
                "def f() -> dict[str, tuple[int, list[str]]]: ...\n", id="return"
            ),
            pytest.param(
                "cache: list[tuple[int, int, list[str]]] = []\n", id="variable"
            ),
            pytest.param(
                "from typing import TypeAlias\n"
                "Alias: TypeAlias = dict[str, tuple[int, list[str]]]\n",
                id="type-alias-value",
            ),
            pytest.param(
                "import typing\n"
                "Alias: typing.TypeAlias = dict[str, tuple[int, list[str]]]\n",
                id="dotted-type-alias-value",
            ),
        ],
    )
    def test_NestedAnnotation_FlagsViolation(self, source: str) -> None:
        violations = list(check_deeply_nested_type(Path("src/x.py"), source))
        assert len(violations) == 1
        assert violations[0].rule == RS_DEEPLY_NESTED_TYPE

    def test_DeeperNesting_ReportsItsDepth(self) -> None:
        source = "def f() -> list[list[dict[str, list[list]]]]: ...\n"
        violations = list(check_deeply_nested_type(Path("src/x.py"), source))
        assert len(violations) == 1
        assert "4 levels" in violations[0].message

    @pytest.mark.skipif(
        sys.version_info < (3, 12),
        reason="the PEP 695 `type` statement parses only on 3.12+",
    )
    def test_Pep695TypeAlias_FlagsViolation(self) -> None:
        source = "type Alias = dict[str, tuple[int, list[str]]]\n"
        violations = list(check_deeply_nested_type(Path("src/x.py"), source))
        assert len(violations) == 1
        assert violations[0].rule == RS_DEEPLY_NESTED_TYPE

    @pytest.mark.parametrize(
        "source",
        [
            pytest.param("def f(x: dict[str, int]) -> None: ...\n", id="one-level"),
            pytest.param(
                "def f(x: dict[str, list[int]]) -> None: ...\n", id="two-level-idiom"
            ),
            pytest.param(
                "def f() -> Iterator[tuple[int, str]]: ...\n", id="iterator-of-tuple"
            ),
            pytest.param("def f(x: int) -> str: ...\n", id="unsubscripted"),
            pytest.param(
                "from typing import TypeAlias\n"
                "Alias: TypeAlias = dict[str, list[int]]\n",
                id="two-level-alias",
            ),
        ],
    )
    def test_ShallowAnnotation_NoViolation(self, source: str) -> None:
        assert list(check_deeply_nested_type(Path("src/x.py"), source)) == []

    def test_NonPythonFile_NotChecked(self) -> None:
        source = "def f(rows: list[list[int]]) -> None: ...\n"
        assert list(check_deeply_nested_type(Path("README.md"), source)) == []
