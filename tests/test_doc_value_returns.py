from pathlib import Path

import pytest

from repostyle.rules import (
    RS_RETURN_DESCRIBED_IN_PROSE,
    check_arg_described_in_prose,
    check_doc_value_signal,
    check_raise_described_in_prose,
    check_raises_section_incomplete,
    check_return_described_in_prose,
)

_SRC = Path("src/x.py")


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
            "def stream_rows(raw: bytes) -> Iterator[dict]:\n"
            '    """Stream parsed rows lazily.\n'
            "\n"
            "    Yields each row as soon as it is parsed.\n"
            '    """\n'
            "    yield {}\n",
            "def stream_rows(raw: bytes) -> Iterator[dict]:\n"
            '    """Stream parsed rows lazily.\n'
            "\n"
            "    Yield the row as soon as it is parsed.\n"
            '    """\n'
            "    yield {}\n",
            "def read_value(value: str) -> str | None:\n"
            '    """Read the tagged value.\n'
            "\n"
            "    Every other shape yields None.\n"
            '    """\n'
            "    return value\n",
            "def load(path: Path) -> Config | None:\n"
            '    """Load the recorded config.\n'
            "\n"
            "    A missing or malformed file returns None rather than "
            "raising.\n"
            '    """\n'
            "    return None\n",
            "def read_value(value: str) -> str | None:\n"
            '    """Read the tagged value.\n'
            "\n"
            "    The result is the body, else None.\n"
            '    """\n'
            "    return value\n",
            "def read_value(value: str) -> str | None:\n"
            '    """Read the tagged value.\n'
            "\n"
            "    The value returned is the parsed body.\n"
            '    """\n'
            "    return value\n",
            "def extract(raw: bytes) -> dict[int, bytes]:\n"
            '    """Extract fields by scanning bytes for pipe delimiters.\n'
            "\n"
            "    The return value is a map of field index to field value.\n"
            '    """\n'
            "    return {}\n",
        ],
        ids=[
            "returns-plural",
            "return-singular",
            "returns-true-if",
            "returns-none",
            "return-self",
            "yields-plural",
            "yield-singular",
            "yields-mid-clause",
            "returns-mid-clause",
            "result-as-subject",
            "value-returned-as-subject",
            "return-value-as-subject",
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
            "def read_value(value: str) -> str | None:\n"
            '    """Read the tagged value.\n'
            "\n"
            "    Anything else gives back None.\n"
            '    """\n'
            "    return value\n",
            "def check_tuple_return(node: ast.AST) -> Iterator[str]:\n"
            '    """Flag a function whose return is an anonymous composite.\n'
            "\n"
            "    A documented function is flagged when it returns a bare "
            "tuple.\n"
            '    """\n'
            '    yield ""\n',
            "def normalize_opening(text: str) -> str:\n"
            '    """Normalize a docstring opening to the house mood.\n'
            "\n"
            "    The house convention is descriptive (`Returns the lease.`), "
            "not\n"
            "    imperative (`Return the lease.`).\n"
            '    """\n'
            "    return text\n",
            "def acquire(pool: Pool) -> Lease:\n"
            '    """Acquire a lease from the pool.\n'
            "\n"
            "    The caller must return the borrowed lease to the pool.\n"
            '    """\n'
            "    return Lease()\n",
            "def acquire(pool: Pool) -> Lease:\n"
            '    """Acquire a lease from the pool.\n'
            "\n"
            "    The result is that the pool loses one free slot.\n"
            '    """\n'
            "    return Lease()\n",
            "def acquire(pool: Pool) -> Lease:\n"
            '    """Acquire a lease from the pool.\n'
            "\n"
            "    The result is cached for the lifetime of the process.\n"
            '    """\n'
            "    return Lease()\n",
        ],
        ids=[
            "has-returns-section",
            "has-yields-section",
            "no-return-annotation",
            "none-annotation",
            "mid-sentence-mention",
            "only-in-summary",
            "return-as-domain-noun",
            "give-back-synonym",
            "pronoun-subject-mid-clause",
            "quoted-example-in-code-span",
            "modal-infinitive-domain-return",
            "result-is-consequence-clause",
            "result-is-participle",
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


def _check(source: str, path: Path = _SRC) -> list:
    return list(check_doc_value_signal(path, source))


def _check_arg(source: str, path: Path = _SRC) -> list:
    return list(check_arg_described_in_prose(path, source))


def _check_raise(source: str, path: Path = _SRC) -> list:
    return list(check_raise_described_in_prose(path, source))


def _check_raises_incomplete(source: str, path: Path = _SRC) -> list:
    return list(check_raises_section_incomplete(path, source))


def _check_return(source: str, path: Path = _SRC) -> list:
    return list(check_return_described_in_prose(path, source))
