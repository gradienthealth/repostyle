from pathlib import Path

import pytest

from pystyle.rules import RS_DOC_VALUE_SIGNAL, check_doc_value_signal

_SRC = Path("src/x.py")


def _check(source: str, path: Path = _SRC) -> list:
    return list(check_doc_value_signal(path, source))


class TestCheckDocValueSignal:
    @pytest.mark.parametrize(
        "source",
        [
            "def process(data):\n"
            "    for item in data:\n"
            "        if item:\n"
            "            if item.ok:\n"
            "                return item\n",
            "def render(a, b, c, d):\n    return a\n",
        ],
        ids=["complexity-floor", "param-floor"],
    )
    def test_NonTrivialUndocumentedFunction_FlagsPresence(self, source: str) -> None:
        violations = _check(source)
        assert len(violations) == 1
        assert violations[0].rule == RS_DOC_VALUE_SIGNAL
        assert "no docstring" in violations[0].message

    def test_TrivialFunction_NoViolation(self) -> None:
        assert _check("def add(a, b):\n    return a + b\n") == []

    def test_DocumentedManyParameterFunction_FlagsArgs(self) -> None:
        source = (
            "def configure(a, b, c, d) -> None:\n"
            '    """Set up the thing."""\n'
            "    return\n"
        )
        violations = _check(source)
        assert len(violations) == 1
        assert "`Args:`" in violations[0].message

    def test_DocstringWithArgsSection_NoViolation(self) -> None:
        source = (
            "def configure(a, b, c, d) -> int:\n"
            '    """Set up the thing.\n'
            "\n"
            "    Args:\n"
            "        a: first.\n"
            "        b: second.\n"
            "        c: third.\n"
            "        d: fourth.\n"
            '    """\n'
            "    return a\n"
        )
        assert _check(source) == []

    def test_DocumentedFewParameterFunction_NoArgsViolation(self) -> None:
        source = 'def fetch(a, b) -> int:\n    """Get the count."""\n    return a + b\n'
        assert _check(source) == []

    def test_DocumentedScalarReturn_NoReturnsViolation(self) -> None:
        source = (
            'def url(self) -> str:\n    """Return the URL."""\n    return self._u\n'
        )
        assert _check(source) == []

    def test_DocumentedTupleReturn_FlagsReturns(self) -> None:
        source = (
            "def plan(target) -> tuple[int, int]:\n"
            '    """Plan the reconcile."""\n'
            "    return target, 0\n"
        )
        violations = _check(source)
        assert len(violations) == 1
        assert "`Returns:`" in violations[0].message

    def test_TupleReturnWithReturnsSection_NoViolation(self) -> None:
        source = (
            "def plan(target) -> tuple[int, int]:\n"
            '    """Plan the reconcile.\n'
            "\n"
            "    Returns:\n"
            "        the target and the current count.\n"
            '    """\n'
            "    return target, 0\n"
        )
        assert _check(source) == []

    @pytest.mark.parametrize(
        "annotation",
        ["tuple[int, ...]", "tuple[int, str, ...]"],
        ids=["homogeneous", "multi-type"],
    )
    def test_VariadicTupleReturn_NoReturnsViolation(self, annotation: str) -> None:
        source = (
            f"def items(n) -> {annotation}:\n"
            '    """Return the items."""\n'
            "    return (n,)\n"
        )
        assert _check(source) == []

    @pytest.mark.parametrize(
        ("source", "path"),
        [
            ("def _helper(a, b, c, d, e):\n    return a\n", _SRC),
            ("def test_it(a, b, c, d):\n    assert a\n", _SRC),
            ("def render(a, b, c, d):\n    return a\n", Path("tests/test_x.py")),
            ("def render(a, b, c, d):\n    return a\n", Path("README.md")),
            (
                "from typing import overload\n@overload\ndef render(a, b, c, d): ...\n",
                _SRC,
            ),
        ],
        ids=["private-name", "test-name", "test-file", "non-python", "overload"],
    )
    def test_ExcludedDefinition_NoViolation(self, source: str, path: Path) -> None:
        assert _check(source, path) == []
