from pathlib import Path

from gradient_pystyle.rules import RS_DOC_VALUE_SIGNAL, check_doc_value_signal

_SRC = Path("src/x.py")


def _check(source: str, path: Path = _SRC) -> list:
    return list(check_doc_value_signal(path, source))


class TestCheckDocValueSignal:
    def test_ComplexUndocumentedFunction_FlagsPresence(self) -> None:
        source = (
            "def process(data):\n"
            "    for item in data:\n"
            "        if item:\n"
            "            if item.ok:\n"
            "                return item\n"
        )
        violations = _check(source)
        assert len(violations) == 1
        assert violations[0].rule == RS_DOC_VALUE_SIGNAL
        assert "no docstring" in violations[0].message

    def test_ManyParameterUndocumentedFunction_FlagsPresence(self) -> None:
        violations = _check("def render(a, b, c, d):\n    return a\n")
        assert len(violations) == 1
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

    def test_VariadicTupleReturn_NoReturnsViolation(self) -> None:
        source = (
            "def items(n) -> tuple[int, ...]:\n"
            '    """Return the items."""\n'
            "    return (n,)\n"
        )
        assert _check(source) == []

    def test_PrivateFunction_NoViolation(self) -> None:
        assert _check("def _helper(a, b, c, d, e):\n    return a\n") == []

    def test_TestFunctionByName_NoViolation(self) -> None:
        assert _check("def test_it(a, b, c, d):\n    assert a\n") == []

    def test_TestFile_NotChecked(self) -> None:
        source = "def render(a, b, c, d):\n    return a\n"
        assert _check(source, Path("tests/test_x.py")) == []

    def test_NonPythonFile_NotChecked(self) -> None:
        source = "def render(a, b, c, d):\n    return a\n"
        assert _check(source, Path("README.md")) == []
