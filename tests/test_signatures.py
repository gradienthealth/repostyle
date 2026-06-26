from pathlib import Path

import pytest

from pystyle.rules import RS_TOO_MANY_POSITIONAL_ARGS, check_too_many_positional_args

_SRC = Path("src/x.py")


class TestCheckTooManyPositionalArgs:
    @pytest.mark.parametrize(
        "source",
        [
            "def free(a, b, c, d, e, f):\n    return a\n",
            "async def free(a, b, c, d, e, f):\n    return a\n",
            "def free(a, b, c, d, e, f, /):\n    return a\n",
            "class C:\n    @staticmethod\n"
            "    def m(a, b, c, d, e, f):\n        return a\n",
            "class C:\n    def m(self, a, b, c, d, e, f):\n        return a\n",
        ],
        ids=[
            "free",
            "async",
            "positional-only",
            "staticmethod",
            "method-excludes-self",
        ],
    )
    def test_DefinitionOverThePositionalLimit_FlagsViolation(self, source: str) -> None:
        violations = _check(source)
        assert len(violations) == 1
        assert violations[0].rule == RS_TOO_MANY_POSITIONAL_ARGS
        assert "6 positional parameters" in violations[0].message

    @pytest.mark.parametrize(
        "source",
        [
            "def free(a, b, c, d, e):\n    return a\n",
            "class C:\n    def m(self, a, b, c, d, e):\n        return a\n",
            "class C:\n    @classmethod\n"
            "    def m(cls, a, b, c, d, e):\n        return cls\n",
        ],
        ids=["free", "method-self", "classmethod-cls"],
    )
    def test_DefinitionAtThePositionalLimit_NoViolation(self, source: str) -> None:
        assert _check(source) == []

    def test_KeywordOnlyArguments_NotCounted(self) -> None:
        source = "def build(*, a, b, c, d, e, f, g):\n    return a\n"
        assert _check(source) == []

    def test_PositionalLimitWithExtraKeywordOnly_NoViolation(self) -> None:
        source = "def f(a, b, c, d, e, *, k1, k2):\n    return a\n"
        assert _check(source) == []

    @pytest.mark.parametrize(
        "decorator",
        ["override", "typing.override"],
        ids=["bare", "dotted"],
    )
    def test_OverrideMethod_Exempt(self, decorator: str) -> None:
        source = (
            "class C:\n"
            f"    @{decorator}\n"
            "    def m(self, a, b, c, d, e, f, g):\n"
            "        return a\n"
        )
        assert _check(source) == []

    def test_NestedFunction_CountedAsFreeFunction(self) -> None:
        source = (
            "def outer():\n"
            "    def inner(a, b, c, d, e, f):\n"
            "        return a\n"
            "    return inner\n"
        )
        violations = _check(source)
        assert len(violations) == 1
        assert violations[0].line == 2

    def test_NonPythonFile_NotChecked(self) -> None:
        source = "def free(a, b, c, d, e, f):\n    return a\n"
        assert _check(source, Path("README.md")) == []


def _check(source: str, path: Path = _SRC) -> list:
    return list(check_too_many_positional_args(path, source))
