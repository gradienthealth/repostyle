from pathlib import Path

import pytest

from repostyle.rules import (
    RS_RAISE_DESCRIBED_IN_PROSE,
    RS_RAISES_SECTION_INCOMPLETE,
    check_arg_described_in_prose,
    check_doc_value_signal,
    check_raise_described_in_prose,
    check_raises_section_incomplete,
    check_return_described_in_prose,
)

_SRC = Path("src/x.py")


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
        "docstring",
        [
            '"""Raises when source evidence changed after review."""',
            (
                '"""Verifies the captured evidence.\n'
                "\n"
                "    Raises if a source changed after capture.\n"
                '    """'
            ),
        ],
        ids=["summary", "body"],
    )
    def test_UnnamedRaiseConditionWithOneExplicitType_FlagsException(
        self, docstring: str
    ) -> None:
        source = (
            "def verify() -> None:\n"
            f"    {docstring}\n"
            "    if changed():\n"
            '        raise ValueError("changed")\n'
        )

        violations = _check_raise(source)

        assert len(violations) == 1
        assert violations[0].rule == RS_RAISE_DESCRIBED_IN_PROSE
        assert "exception 'ValueError'" in violations[0].message

    def test_UnnamedRaiseCondition_LeavesMissingTypeToRS041(self) -> None:
        source = (
            "def verify() -> None:\n"
            '    """Raises when source evidence changes.\n'
            "\n"
            "    Raises:\n"
            "        KeyError: If required evidence is missing.\n"
            '    """\n'
            "    if changed():\n"
            '        raise ValueError("changed")\n'
        )

        prose_violations = _check_raise(source)
        section_violations = _check_raises_incomplete(source)

        assert len(prose_violations) == 1
        assert prose_violations[0].rule == RS_RAISE_DESCRIBED_IN_PROSE
        assert "exception 'ValueError'" in prose_violations[0].message
        assert section_violations == []

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
            "def adjust(value: int) -> None:\n"
            '    """Raises the threshold when the input is positive."""\n'
            "    if value > 0:\n"
            '        raise ValueError("unsupported")\n',
            "def monitor(alarm) -> None:\n"
            '    """The alarm raises when the sensor disconnects."""\n'
            "    if alarm.disconnected:\n"
            '        raise ValueError("disconnected")\n',
            "def verify(exc) -> None:\n"
            '    """Raises when source evidence changes."""\n'
            "    raise exc\n",
            "def verify() -> None:\n"
            '    """Raises when source evidence changes."""\n'
            "    if missing():\n"
            '        raise ValueError("missing")\n'
            '    raise TypeError("invalid")\n',
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
            "domain-object",
            "domain-subject",
            "no-static-type",
            "multiple-static-types",
        ],
    )
    def test_RaiseNotDescribedInProse_NoViolation(self, source: str) -> None:
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


def _check_raise(source: str, path: Path = _SRC) -> list:
    return list(check_raise_described_in_prose(path, source))


def _check_raises_incomplete(source: str, path: Path = _SRC) -> list:
    return list(check_raises_section_incomplete(path, source))


def _check_return(source: str, path: Path = _SRC) -> list:
    return list(check_return_described_in_prose(path, source))
