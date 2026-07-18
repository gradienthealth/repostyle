from pathlib import Path

import pytest

from repostyle.rules import (
    RS_ARG_DESCRIBED_IN_PROSE,
    RS_DOC_VALUE_SIGNAL,
    RS_RAISE_DESCRIBED_IN_PROSE,
    RS_RAISES_SECTION_INCOMPLETE,
    RS_RETURN_DESCRIBED_IN_PROSE,
    check_arg_described_in_prose,
    check_doc_value_signal,
    check_raise_described_in_prose,
    check_raises_section_incomplete,
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
            (
                "def read(count):\n"
                '    """Read a chunk.\n'
                "\n"
                "    Sizes the `buffer in bytes. The `count` is the item total.\n"
                '    """\n'
                "    return count\n",
                {"count"},
            ),
        ],
        ids=["single", "args-section-omits-it", "several", "unbalanced-backtick"],
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
        """The verdict does not shift with where the body prose wraps."""
        # `base` opens a wrapped continuation line but sits mid-sentence (a
        # comma precedes it), so it is not the subject.
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
            "def find(key: str) -> Widget | None:\n"
            '    """Look up a widget by key.\n'
            "\n"
            "    Returns None when no widget matches the key.\n"
            '    """\n'
            "    return None\n",
            "def with_timeout(self, seconds: float) -> Client:\n"
            '    """Configure the request timeout.\n'
            "\n"
            "    Return self so calls can chain.\n"
            '    """\n'
            "    return self\n",
        ],
        ids=[
            "returns-plural",
            "return-singular",
            "returns-true-if",
            "returns-none",
            "return-self",
        ],
    )
    def test_ReturnDescribedInBodyProse_FlagsViolation(self, source: str) -> None:
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
            "def stream_rows(raw: bytes) -> Iterator[dict]:\n"
            '    """Stream parsed rows lazily.\n'
            "\n"
            "    Yields:\n"
            "        Each row as a dict as soon as it is parsed.\n"
            '    """\n'
            "    yield {}\n",
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
            "has-yields-section",
            "no-return-annotation",
            "none-annotation",
            "mid-sentence-mention",
            "only-in-summary",
            "return-as-domain-noun",
        ],
    )
    def test_ReturnNotDescribedInBodyProse_NoViolation(self, source: str) -> None:
        assert _check_return(source) == []

    def test_PrivateDefinition_NoViolation(self) -> None:
        """Smoke-checks that RS032 also routes through `_public_functions`.

        The private/test-name/test-file/overload filtering is exhaustively
        covered by the identical case in `TestCheckArgDescribedInProse` above.
        """
        source = (
            "def _extract(raw: bytes) -> dict[int, bytes]:\n"
            '    """Extract fields.\n\n    Returns a dict of fields.\n    """\n'
            "    return {}\n"
        )
        assert _check_return(source) == []


class TestCheckRaiseDescribedInProse:
    @pytest.mark.parametrize(
        ("source", "name"),
        [
            (
                "def categorize(client) -> Plan:\n"
                '    """Categorize the bundle, auditing the crossing.\n'
                "\n"
                "    A failure emits a failure audit event and re-raises the\n"
                "    `CategorizerError` rather than swallowing it.\n"
                '    """\n'
                "    return client.categorize()\n",
                "CategorizerError",
            ),
            (
                "def parse(raw: bytes) -> int:\n"
                '    """Parse the header.\n'
                "\n"
                "    Raises `ValueError` when the input is empty.\n"
                '    """\n'
                "    return 0\n",
                "ValueError",
            ),
            (
                "def fetch(url: str) -> bytes:\n"
                '    """Fetch the resource.\n'
                "\n"
                "    A timeout propagates the client's `TimeoutError` to the "
                "caller.\n"
                '    """\n'
                "    return b''\n",
                "TimeoutError",
            ),
            (
                "def load(path: str) -> dict:\n"
                '    """Load the config.\n'
                "\n"
                "    A missing key raises `KeyError` during validation.\n"
                "\n"
                "    Raises:\n"
                "        ValueError: when the file is not valid TOML.\n"
                '    """\n'
                "    return {}\n",
                "KeyError",
            ),
            (
                "def fetch(url: str) -> bytes:\n"
                '    """Fetch the resource.\n'
                "\n"
                "    A timeout propagates the client's `pkg.mod.TimeoutError`.\n"
                '    """\n'
                "    return b''\n",
                "pkg.mod.TimeoutError",
            ),
        ],
        ids=[
            "re-raises-mid-clause",
            "raises-lead",
            "propagates",
            "raises-section-omits-it",
            "dotted-name-in-prose",
        ],
    )
    def test_RaiseDescribedInBodyProse_FlagsException(
        self, source: str, name: str
    ) -> None:
        violations = _check_raise(source)
        assert len(violations) == 1
        assert violations[0].rule == RS_RAISE_DESCRIBED_IN_PROSE
        assert f"exception '{name}'" in violations[0].message
        assert "`Raises:`" in violations[0].message

    @pytest.mark.parametrize(
        "source",
        [
            "def parse(raw: bytes) -> int:\n"
            '    """Parse the header.\n'
            "\n"
            "    An empty input raises `ValueError` before any field is read.\n"
            "\n"
            "    Raises:\n"
            "        ValueError: when the input is empty.\n"
            '    """\n'
            "    return 0\n",
            "def parse(raw: bytes) -> int:\n"
            '    """Parse the header.\n'
            "\n"
            "    An empty input raises `ParseError` before any field is read.\n"
            "\n"
            "    Raises:\n"
            "        errors.ParseError: when the input is empty.\n"
            '    """\n'
            "    return 0\n",
            "def parse(raw: bytes) -> int:\n"
            '    """Parse the header.\n'
            "\n"
            "    An empty input raises `errors.ParseError` on the first field.\n"
            "\n"
            "    Raises:\n"
            "        ParseError: when the input is empty.\n"
            '    """\n'
            "    return 0\n",
            "def peek(queue) -> int:\n"
            '    """Peek at the next item.\n'
            "\n"
            "    This helper never raises `IndexError`; an empty queue yields "
            "zero.\n"
            '    """\n'
            "    return 0\n",
            "def sync(client) -> None:\n"
            '    """Sync the pending records.\n'
            "\n"
            "    A conflict is logged rather than raising `SyncError`, so the "
            "batch\n"
            "    completes.\n"
            '    """\n'
            "    return None\n",
            "def parse(raw: bytes) -> int:\n"
            '    """Parse the header.\n'
            "\n"
            "    Raises when the input is empty rather than guessing a "
            "default.\n"
            '    """\n'
            "    return 0\n",
            "def parse(raw: bytes) -> int:\n"
            '    """Parse the header.\n'
            "\n"
            "    The `ValueError` message names the offending field.\n"
            '    """\n'
            "    return 0\n",
            "def parse(raw: bytes) -> int:\n"
            '    """Parse the header.\n'
            "\n"
            "    The parser raises on a malformed field. The `ValueError` "
            "message\n"
            "    names the offender.\n"
            '    """\n'
            "    return 0\n",
            "def parse(raw: bytes) -> int:\n"
            '    """Raise `ValueError` when the input is empty."""\n'
            "    return 0\n",
            "def parse(raw: bytes) -> int:\n"
            '    """Parse the header.\n'
            "\n"
            "    Raises on any `malformed input. The `ValueError` from the pool "
            "is logged, not propagated.\n"
            '    """\n'
            "    return 0\n",
        ],
        ids=[
            "documented-in-raises",
            "dotted-entry-matches",
            "dotted-prose-matches-bare-entry",
            "negated-never",
            "negated-rather-than-raising",
            "verb-without-exception-name",
            "name-without-raise-verb",
            "verb-and-name-in-separate-sentences",
            "only-in-summary",
            "unbalanced-backtick-falls-back",
        ],
    )
    def test_RaiseNotDescribedInBodyProse_NoViolation(self, source: str) -> None:
        assert _check_raise(source) == []

    def test_PrivateDefinition_NoViolation(self) -> None:
        """Smoke-checks that RS041 also routes through `_public_functions`.

        The private/test-name/test-file/overload filtering is exhaustively
        covered by the identical case in `TestCheckArgDescribedInProse` above.
        """
        source = (
            "def _parse(raw: bytes) -> int:\n"
            '    """Parse the header.\n'
            "\n"
            "    Raises `ValueError` when the input is empty.\n"
            '    """\n'
            "    return 0\n"
        )
        assert _check_raise(source) == []


class TestCheckRaisesSectionIncomplete:
    @pytest.mark.parametrize(
        ("source", "name"),
        [
            (
                "def load(path: str) -> dict:\n"
                '    """Load the config.\n'
                "\n"
                "    Raises:\n"
                "        ValueError: when the file is not valid TOML.\n"
                '    """\n'
                "    if not path:\n"
                '        raise KeyError("missing")\n'
                "    return {}\n",
                "KeyError",
            ),
            (
                "def load(path: str) -> dict:\n"
                '    """Load the config.\n'
                "\n"
                "    Raises:\n"
                "        ValueError: when the file is not valid TOML.\n"
                '    """\n'
                '    raise errors.ParseError("bad")\n',
                "ParseError",
            ),
            (
                "def load(path: str) -> dict:\n"
                '    """Load the config.\n'
                "\n"
                "    Raises:\n"
                "        ValueError: when the file is not valid TOML.\n"
                '    """\n'
                "    raise ConfigError\n",
                "ConfigError",
            ),
        ],
        ids=["call-raise", "dotted-raise", "bare-class-raise"],
    )
    def test_RaisedTypeMissingFromSection_FlagsException(
        self, source: str, name: str
    ) -> None:
        violations = _check_raises_incomplete(source)
        assert len(violations) == 1
        assert violations[0].rule == RS_RAISES_SECTION_INCOMPLETE
        assert f"raises '{name}'" in violations[0].message
        assert "`Raises:`" in violations[0].message

    def test_TwoMissingTypes_FlagsEachInSourceOrder(self) -> None:
        source = (
            "def load(path: str) -> dict:\n"
            '    """Load the config.\n'
            "\n"
            "    Raises:\n"
            "        ValueError: when the file is not valid TOML.\n"
            '    """\n'
            "    if not path:\n"
            '        raise KeyError("missing")\n'
            '    raise RuntimeError("boom")\n'
        )
        violations = _check_raises_incomplete(source)
        assert len(violations) == 2
        assert "KeyError" in violations[0].message
        assert "RuntimeError" in violations[1].message

    @pytest.mark.parametrize(
        "source",
        [
            "def load(path: str) -> dict:\n"
            '    """Load the config.\n'
            "\n"
            "    Raises:\n"
            "        KeyError: when the key is missing.\n"
            '    """\n'
            '    raise KeyError("missing")\n',
            "def load(path: str) -> dict:\n"
            '    """Load the config.\n'
            "\n"
            "    Raises:\n"
            "        errors.ParseError: on a malformed file.\n"
            '    """\n'
            '    raise errors.ParseError("bad")\n',
            "def load(path: str) -> dict:\n"
            '    """Load the config."""\n'
            '    raise KeyError("missing")\n',
            "def reraise() -> None:\n"
            '    """Re-raise the caught error.\n'
            "\n"
            "    Raises:\n"
            "        ValueError: always.\n"
            '    """\n'
            "    try:\n"
            "        risky()\n"
            "    except ValueError:\n"
            "        raise\n",
            "def rethrow(exc) -> None:\n"
            '    """Re-raise the given error.\n'
            "\n"
            "    Raises:\n"
            "        ValueError: always.\n"
            '    """\n'
            "    raise exc\n",
            "def parse(raw: bytes) -> int:\n"
            '    """Parse the header.\n'
            "\n"
            "    An empty input raises `KeyError` before any field is read.\n"
            "\n"
            "    Raises:\n"
            "        ValueError: when the input is malformed.\n"
            '    """\n'
            '    raise KeyError("empty")\n',
            "def _load(path: str) -> dict:\n"
            '    """Load the config.\n'
            "\n"
            "    Raises:\n"
            "        ValueError: when the file is not valid TOML.\n"
            '    """\n'
            '    raise KeyError("missing")\n',
        ],
        ids=[
            "listed-in-section",
            "dotted-entry-matches",
            "no-raises-section",
            "bare-reraise",
            "lowercase-alias",
            "narrated-yields-to-rs041",
            "private-definition",
        ],
    )
    def test_SectionCompleteOrOutOfScope_NoViolation(self, source: str) -> None:
        assert _check_raises_incomplete(source) == []


def _check(source: str, path: Path = _SRC) -> list:
    return list(check_doc_value_signal(path, source))


def _check_arg(source: str, path: Path = _SRC) -> list:
    return list(check_arg_described_in_prose(path, source))


def _check_return(source: str, path: Path = _SRC) -> list:
    return list(check_return_described_in_prose(path, source))


def _check_raise(source: str, path: Path = _SRC) -> list:
    return list(check_raise_described_in_prose(path, source))


def _check_raises_incomplete(source: str, path: Path = _SRC) -> list:
    return list(check_raises_section_incomplete(path, source))
