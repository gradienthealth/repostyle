from pathlib import Path

import pytest

from repostyle.rules import (
    RS_ARG_DESCRIBED_IN_PROSE,
    RS_DOC_VALUE_SIGNAL,
    RS_RETURN_DESCRIBED_IN_PROSE,
    check_arg_described_in_prose,
    check_doc_value_signal,
    check_return_described_in_prose,
)

_SRC = Path("src/x.py")


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

    def test_DocumentedManyParameterFunctionWithoutArgs_NoViolation(self) -> None:
        source = (
            "def configure(a, b, c, d) -> None:\n"
            '    """Set up the thing."""\n'
            "    return\n"
        )
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


class TestCheckArgDescribedInProse:
    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            (
                "def fetch(handle):\n"
                '    """Open a connection.\n'
                "\n"
                "    The `handle` selects which pool to draw from.\n"
                '    """\n'
                "    return handle\n",
                {"handle"},
            ),
            (
                "def fetch(handle, pool):\n"
                '    """Open a connection.\n'
                "\n"
                "    The `pool` is chosen lazily.\n"
                "\n"
                "    Args:\n"
                "        handle: the connection handle.\n"
                '    """\n'
                "    return handle\n",
                {"pool"},
            ),
            (
                "def merge(left, right):\n"
                '    """Combine two sequences.\n'
                "\n"
                "    The `left` wins ties; the `right` fills gaps.\n"
                '    """\n'
                "    return left\n",
                {"left", "right"},
            ),
        ],
        ids=["single", "args-section-omits-it", "several"],
    )
    def test_ParamDescribedInBodyProse_FlagsEach(
        self, source: str, expected: set[str]
    ) -> None:
        violations = _check_arg(source)
        assert len(violations) == len(expected)
        assert all(
            v.rule == RS_ARG_DESCRIBED_IN_PROSE and "`Args:`" in v.message
            for v in violations
        )
        assert all(
            any(f"parameter '{name}'" in v.message for v in violations)
            for name in expected
        )

    @pytest.mark.parametrize(
        "source",
        [
            'def fetch(handle):\n    """Open the `handle` connection."""\n'
            "    return handle\n",
            "def fetch(handle):\n"
            '    """Open a connection.\n'
            "\n"
            "    The handle selects which pool to draw from.\n"
            '    """\n'
            "    return handle\n",
            "def fetch(handle):\n"
            '    """Open a connection.\n'
            "\n"
            "    Args:\n"
            "        handle: which pool to draw from.\n"
            '    """\n'
            "    return handle\n",
            'def fetch(handle):\n    """Open a connection."""\n    return handle\n',
            "def run(path):\n"
            '    """Reflow the findings in `path`.\n'
            "\n"
            "    A no-op unless `path` is a Python file.\n"
            '    """\n'
            "    return path\n",
            "def changed(path, base):\n"
            '    """Return the lines `path` adds versus `base`.\n'
            "\n"
            "    Return nothing when `base` is unknown or `path` is untracked.\n"
            '    """\n'
            "    return base\n",
        ],
        ids=[
            "only-in-summary",
            "not-backticked",
            "documented-in-args",
            "no-body",
            "object-not-subject",
            "listed-mid-clause",
        ],
    )
    def test_ParamNotDescribedInBodyProse_NoViolation(self, source: str) -> None:
        assert _check_arg(source) == []

    def test_ParamOpeningWrappedLineMidSentence_NoViolation(self) -> None:
        # `base` opens a wrapped continuation line but sits mid-sentence (a
        # comma precedes it), so it is not the subject; the verdict must not
        # shift with where the prose happens to wrap.
        source = (
            "def diff(path, base):\n"
            '    """Return the changed lines.\n\n'
            "    Return None when the set is untrusted — git is unavailable,\n"
            "    `base` is unknown, or path is untracked — so the caller\n"
            "    reports every finding.\n"
            '    """\n    return path\n'
        )
        assert _check_arg(source) == []

    @pytest.mark.parametrize(
        ("source", "path"),
        [
            (
                "def _fetch(handle):\n"
                '    """Open a connection.\n\n    The `handle` picks a pool.\n'
                '    """\n    return handle\n',
                _SRC,
            ),
            (
                "def test_fetch(handle):\n"
                '    """Open a connection.\n\n    The `handle` picks a pool.\n'
                '    """\n    return handle\n',
                _SRC,
            ),
            (
                "def fetch(handle):\n"
                '    """Open a connection.\n\n    The `handle` picks a pool.\n'
                '    """\n    return handle\n',
                Path("tests/test_x.py"),
            ),
            (
                "from typing import overload\n"
                "@overload\n"
                "def fetch(handle):\n"
                '    """Open a connection.\n\n    The `handle` picks a pool.\n'
                '    """\n',
                _SRC,
            ),
        ],
        ids=["private-name", "test-name", "test-file", "overload"],
    )
    def test_ExcludedDefinition_NoViolation(self, source: str, path: Path) -> None:
        assert _check_arg(source, path) == []


class TestCheckReturnDescribedInProse:
    @pytest.mark.parametrize(
        "source",
        [
            "def extract(raw: bytes) -> dict[int, bytes]:\n"
            '    """Extract fields by scanning bytes for pipe delimiters.\n'
            "\n"
            "    Returns a dict mapping field index to field value bytes. Per "
            "spec,\n"
            "    field 1 is the separator.\n"
            '    """\n'
            "    return {}\n",
            "def parse(raw: bytes) -> int:\n"
            '    """Parse the header.\n'
            "\n"
            "    Return the parsed value.\n"
            '    """\n'
            "    return 0\n",
            "def is_ready(raw: bytes) -> bool:\n"
            '    """Check readiness.\n'
            "\n"
            "    Returns True if the record is valid.\n"
            '    """\n'
            "    return True\n",
            "def stream_rows(raw: bytes) -> Iterator[dict]:\n"
            '    """Stream parsed rows lazily.\n'
            "\n"
            "    Returns each row as a dict as soon as it is parsed.\n"
            '    """\n'
            "    yield {}\n",
        ],
        ids=["returns-plural", "return-singular", "returns-true-if", "generator"],
    )
    def test_ReturnDescribedInBodyProse_Flags(self, source: str) -> None:
        violations = _check_return(source)
        assert len(violations) == 1
        assert violations[0].rule == RS_RETURN_DESCRIBED_IN_PROSE
        assert "`Returns:`/`Yields:`" in violations[0].message

    @pytest.mark.parametrize(
        "source",
        [
            "def extract(raw: bytes) -> dict[int, bytes]:\n"
            '    """Extract fields by scanning bytes for pipe delimiters.\n'
            "\n"
            "    Returns:\n"
            "        A dict mapping field index to field value bytes.\n"
            '    """\n'
            "    return {}\n",
            "def extract(raw: bytes):\n"
            '    """Extract fields by scanning bytes for pipe delimiters.\n'
            "\n"
            "    Returns a dict mapping field index to field value bytes.\n"
            '    """\n'
            "    return {}\n",
            "def run(raw: bytes) -> None:\n"
            '    """Run the extraction.\n'
            "\n"
            "    Returns nothing; the result is logged instead.\n"
            '    """\n'
            "    return None\n",
            "def extract(raw: bytes) -> dict[int, bytes]:\n"
            '    """Extract fields by scanning bytes for pipe delimiters.\n'
            "\n"
            "    The caller then decides how the map returns to the pool.\n"
            '    """\n'
            "    return {}\n",
            "def extract(raw: bytes) -> dict[int, bytes]:\n"
            '    """Return a dict mapping field index to field value bytes."""\n'
            "    return {}\n",
            "def extract(raw: bytes) -> dict[int, bytes]:\n"
            '    """Extract fields by scanning bytes for pipe delimiters."""\n'
            "    return {}\n",
            "def schedule_return_visit(patient_id: str) -> Appointment:\n"
            '    """Schedule a follow-up visit.\n'
            "\n"
            "    Return visits are limited to once every 30 days per payer "
            "policy.\n"
            '    """\n'
            "    return Appointment()\n",
        ],
        ids=[
            "has-returns-section",
            "no-return-annotation",
            "none-annotation",
            "mid-sentence-mention",
            "only-in-summary",
            "no-body",
            "return-as-domain-noun",
        ],
    )
    def test_ReturnNotDescribedInBodyProse_NoViolation(self, source: str) -> None:
        assert _check_return(source) == []

    @pytest.mark.parametrize(
        ("source", "path"),
        [
            (
                "def _extract(raw: bytes) -> dict[int, bytes]:\n"
                '    """Extract fields.\n\n    Returns a dict of fields.\n"""\n'
                "    return {}\n",
                _SRC,
            ),
            (
                "def test_extract(raw: bytes) -> dict[int, bytes]:\n"
                '    """Extract fields.\n\n    Returns a dict of fields.\n"""\n'
                "    return {}\n",
                _SRC,
            ),
            (
                "def extract(raw: bytes) -> dict[int, bytes]:\n"
                '    """Extract fields.\n\n    Returns a dict of fields.\n"""\n'
                "    return {}\n",
                Path("tests/test_x.py"),
            ),
            (
                "from typing import overload\n"
                "@overload\n"
                "def extract(raw: bytes) -> dict[int, bytes]:\n"
                '    """Extract fields.\n\n    Returns a dict of fields.\n"""\n',
                _SRC,
            ),
        ],
        ids=["private-name", "test-name", "test-file", "overload"],
    )
    def test_ExcludedDefinition_NoViolation(self, source: str, path: Path) -> None:
        assert _check_return(source, path) == []


def _check(source: str, path: Path = _SRC) -> list:
    return list(check_doc_value_signal(path, source))


def _check_arg(source: str, path: Path = _SRC) -> list:
    return list(check_arg_described_in_prose(path, source))


def _check_return(source: str, path: Path = _SRC) -> list:
    return list(check_return_described_in_prose(path, source))
