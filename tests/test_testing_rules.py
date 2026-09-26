import sys
from pathlib import Path

import pytest

from repostyle.rules import (
    RS_BEHAVIOR_VERIFICATION_ONLY,
    RS_CONDITIONAL_TEST_LOGIC,
    RS_EXCESSIVE_MOCKING,
    RS_FILE_LITERAL_RESTATEMENT,
    RS_NO_MOCK_PATCH,
    RS_SLEEPY_TEST,
    check_behavior_verification_only,
    check_conditional_test_logic,
    check_excessive_mocking,
    check_file_literal_restatement,
    check_no_mock_patch,
    check_sleepy_test,
)

# PEP 695 type-alias / type-parameter syntax only parses on Python 3.12+, so
# these cases skip on 3.11, where the source is a SyntaxError the checker
# correctly cannot inspect (such code cannot exist on 3.11 anyway).
_REQUIRES_PEP695 = pytest.mark.skipif(
    sys.version_info < (3, 12), reason="PEP 695 syntax requires Python 3.12+"
)

_ATTRIBUTES_BLOCK_HEADER = (
    "class Demographics:\n"
    '    """Patient demographics.\n'
    "\n"
    "    Attributes:\n"
    "        name: full name.\n"
    '    """\n'
)
_ATTRIBUTES_NO_BLOCK = 'class Demographics:\n    """Patient demographics."""\n'
_ATTRIBUTES_INLINE_PROSE = (
    "class Demographics:\n"
    '    """Mentions Attributes: inline but not as section header."""\n'
)
_TEST_PATH = Path("tests/unit/test_x.py")


class TestCheckNoMockPatch:
    @pytest.mark.parametrize(
        "source",
        [
            "import unittest.mock",
            "from unittest.mock import patch",
            "from unittest.mock import MagicMock",
            "import mock",
        ],
    )
    def test_ImportOfMock_FlagsViolation(self, source: str) -> None:
        violations = list(check_no_mock_patch(_TEST_PATH, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_NO_MOCK_PATCH

    def test_FromUnittestImportMock_FlagsViolation(self) -> None:
        violations = list(check_no_mock_patch(_TEST_PATH, "from unittest import mock"))
        assert len(violations) == 1
        assert violations[0].rule == RS_NO_MOCK_PATCH

    def test_NonMockImport_NoViolation(self) -> None:
        source = "from collections import OrderedDict"
        assert list(check_no_mock_patch(_TEST_PATH, source)) == []

    def test_InsideTestsFakes_NotChecked(self) -> None:
        source = "import unittest.mock"
        path = Path("tests/fakes/fake_x.py")
        assert list(check_no_mock_patch(path, source)) == []


class TestCheckConditionalTestLogic:
    @pytest.mark.parametrize(
        "body",
        [
            "    if cond:\n        assert result\n",
            "    for item in items:\n        assert item\n",
            "    while pending:\n        assert pending\n",
            "    try:\n        assert run()\n    except ValueError:\n        pass\n",
        ],
        ids=["if", "for", "while", "try"],
    )
    def test_AssertInsideControlFlow_FlagsViolation(self, body: str) -> None:
        source = f"def test_Thing_Behaves():\n{body}"
        violations = list(check_conditional_test_logic(_TEST_PATH, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_CONDITIONAL_TEST_LOGIC

    @pytest.mark.parametrize(
        "source",
        [
            "def test_Thing_Behaves():\n    assert compute() == 3\n",
            (
                "def test_Thing_Behaves():\n"
                "    with pytest.raises(ValueError):\n        run()\n"
            ),
            "def helper():\n    if cond:\n        assert thing\n",
        ],
        ids=["straight_line", "raises_context", "non_test_function"],
    )
    def test_StraightLineOrNonTest_NoViolation(self, source: str) -> None:
        assert list(check_conditional_test_logic(_TEST_PATH, source)) == []

    def test_NonTestFile_NotChecked(self) -> None:
        source = "def test_Thing_Behaves():\n    if cond:\n        assert thing\n"
        assert list(check_conditional_test_logic(Path("src/x.py"), source)) == []


class TestCheckSleepyTest:
    @pytest.mark.parametrize(
        "call",
        ["time.sleep(1)", "asyncio.sleep(0.1)", "asyncio.sleep(delay)"],
        ids=["time", "asyncio", "non_literal_delay"],
    )
    def test_SleepCallInTest_FlagsViolation(self, call: str) -> None:
        source = f"def test_Thing_Behaves():\n    {call}\n"
        violations = list(check_sleepy_test(_TEST_PATH, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_SLEEPY_TEST

    @pytest.mark.parametrize(
        "source",
        [
            "def test_Thing_Behaves():\n    widget.sleep(1)\n",
            "def test_Thing_Behaves():\n    assert awake()\n",
        ],
        ids=["unrelated_sleep_method", "no_sleep"],
    )
    def test_NoModuleSleep_NoViolation(self, source: str) -> None:
        assert list(check_sleepy_test(_TEST_PATH, source)) == []

    @pytest.mark.parametrize(
        "call",
        ["asyncio.sleep(0)", "time.sleep(0)", "asyncio.sleep(0.0)"],
        ids=["asyncio_zero", "time_zero", "asyncio_zero_float"],
    )
    def test_ZeroSleepCall_NoViolation(self, call: str) -> None:
        source = f"def test_Thing_Behaves():\n    {call}\n"
        assert list(check_sleepy_test(_TEST_PATH, source)) == []


class TestCheckExcessiveMocking:
    def test_ManyMocks_FlagsViolation(self) -> None:
        source = (
            "def test_Thing_Behaves():\n"
            "    a = Mock()\n"
            "    b = MagicMock()\n"
            "    c = AsyncMock()\n"
            "    d = patch('x')\n"
        )
        violations = list(check_excessive_mocking(_TEST_PATH, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_EXCESSIVE_MOCKING
        assert "4 mocks" in violations[0].message

    def test_FewMocks_NoViolation(self) -> None:
        source = "def test_Thing_Behaves():\n    a = Mock()\n    b = MagicMock()\n"
        assert list(check_excessive_mocking(_TEST_PATH, source)) == []


class TestCheckBehaviorVerificationOnly:
    def test_OnlyChoreographyAsserts_FlagsViolation(self) -> None:
        source = (
            "def test_Thing_Behaves():\n"
            "    run()\n"
            "    sink.assert_called_once_with(3)\n"
        )
        violations = list(check_behavior_verification_only(_TEST_PATH, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_BEHAVIOR_VERIFICATION_ONLY

    @pytest.mark.parametrize(
        "source",
        [
            (
                "def test_Thing_Behaves():\n    sink.assert_called_once()\n"
                "    assert sink.total == 3\n"
            ),
            "def test_Thing_Behaves():\n    assert compute() == 3\n",
        ],
        ids=["choreography_plus_state", "state_only"],
    )
    def test_AnyStateAssert_NoViolation(self, source: str) -> None:
        assert list(check_behavior_verification_only(_TEST_PATH, source)) == []


_RESTATEMENT_HEADER = (
    "import yaml\n"
    "from pathlib import Path\n"
    "\n"
    "_ROOT = Path(__file__).resolve().parents[2]\n"
    '_COMPOSE = _ROOT / "compose.yaml"\n'
    '_WORKFLOW = _ROOT / "ci.yaml"\n'
    "\n"
    "\n"
    "def _compose():\n"
    "    return yaml.safe_load(_COMPOSE.read_text())\n"
    "\n"
    "\n"
)


class TestCheckFileLiteralRestatement:
    @pytest.mark.parametrize(
        "body",
        [
            '    assert _compose()["services"]["drain"]["user"] == "1000:1000"\n',
            '    assert "healthcheck" not in _compose()["services"]["drain"]\n',
            '    rules = _compose()["command"]\n'
            '    assert rules.index("- *.part") < rules.index("+ [0-9]*/**")\n',
        ],
        ids=["scalar_literal", "membership_literal", "ordering_of_read_strings"],
    )
    def test_AssertionOverOneReadFile_FlagsViolation(self, body: str) -> None:
        source = f"{_RESTATEMENT_HEADER}def test_Drain_RunsAsUser():\n{body}"
        violations = list(check_file_literal_restatement(_TEST_PATH, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_FILE_LITERAL_RESTATEMENT

    def test_FixtureSuppliedFile_FlagsViolation(self) -> None:
        source = (
            f"{_RESTATEMENT_HEADER}"
            "class TestDrain:\n"
            "    @pytest.fixture\n"
            "    def drain(self):\n"
            '        return _compose()["services"]["drain"]\n'
            "\n"
            "    def test_Drain_RunsAsUser(self, drain):\n"
            '        assert drain["user"] == "1000:1000"\n'
        )
        violations = list(check_file_literal_restatement(_TEST_PATH, source))
        assert len(violations) == 1
        assert violations[0].line == _line_of(source, "    def test_Drain_RunsAsUser")

    def test_HelperTakingArguments_FlagsViolation(self) -> None:
        source = (
            f"{_RESTATEMENT_HEADER}"
            "def _service(compose, name):\n"
            "    return compose[name]\n"
            "\n\n"
            "def test_Drain_RunsAsUser():\n"
            '    assert _service(_compose(), "drain")["user"] == "1000:1000"\n'
        )
        violations = list(check_file_literal_restatement(_TEST_PATH, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_FILE_LITERAL_RESTATEMENT

    @pytest.mark.parametrize(
        "body",
        [
            "    workflow = yaml.safe_load(_WORKFLOW.read_text())\n"
            '    assert _compose()["image"] == workflow["image"]\n',
            '    services = _compose()["services"]\n'
            '    assert [name for name in services if "user" not in services[name]] == []\n',
            "    assert _COMPOSE.stat().st_mode & 0o111 == 0\n",
            "    assert render(_compose()) == 3\n",
        ],
        ids=["two_files", "property_over_entries", "file_metadata", "exercises_code"],
    )
    def test_AssertionBeyondOneFilesLiterals_NoViolation(self, body: str) -> None:
        source = (
            f"{_RESTATEMENT_HEADER}from myapp import render\n"
            f"\n\ndef test_Drain_RunsAsUser():\n{body}"
        )
        assert list(check_file_literal_restatement(_TEST_PATH, source)) == []

    def test_ConstantHoldingThePathString_NoViolation(self) -> None:
        """A string spelling `Path` is not a `Path` expression."""
        source = (
            'import yaml\nfrom pathlib import Path\n\n_LABEL = "Path"\n\n\n'
            "def test_Label_IsCanonical():\n"
            '    assert _LABEL.lower() == "path"\n'
        )
        assert list(check_file_literal_restatement(_TEST_PATH, source)) == []

    @pytest.mark.parametrize(
        "signature",
        ["shared_compose", "*, shared_compose", "shared_compose, /"],
        ids=["positional", "keyword_only", "positional_only"],
    )
    def test_FixtureFromAnotherModule_NoViolation(self, signature: str) -> None:
        source = (
            f"{_RESTATEMENT_HEADER}def test_Drain_RunsAsUser({signature}):\n"
            '    assert _compose()["user"] == "1000"\n'
        )
        assert list(check_file_literal_restatement(_TEST_PATH, source)) == []

    def test_InertPytestFixture_FlagsViolation(self) -> None:
        """`tmp_path` supplies a temporary directory, never a repo file."""
        source = (
            f"{_RESTATEMENT_HEADER}def test_Drain_RunsAsUser(tmp_path):\n"
            '    assert _compose()["user"] == "1000"\n'
        )
        violations = list(check_file_literal_restatement(_TEST_PATH, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_FILE_LITERAL_RESTATEMENT

    def test_ConftestFixture_ResolvesAndFlagsViolation(self, tmp_path: Path) -> None:
        conftest = tmp_path / "conftest.py"
        conftest.write_text(
            "import pytest\nimport yaml\nfrom pathlib import Path\n\n"
            '_COMPOSE = Path(__file__).parent / "compose.yaml"\n\n\n'
            "@pytest.fixture\ndef drain():\n"
            '    return yaml.safe_load(_COMPOSE.read_text())["drain"]\n'
        )
        test_file = tmp_path / "test_drain.py"
        source = (
            "def test_Drain_RunsAsUser(drain):\n"
            '    assert drain["user"] == "1000:1000"\n'
        )
        test_file.write_text(source)

        violations = list(check_file_literal_restatement(test_file, source))

        assert len(violations) == 1
        assert violations[0].rule == RS_FILE_LITERAL_RESTATEMENT

    def test_ConftestFixtureBuildingAProductObject_NoViolation(
        self, tmp_path: Path
    ) -> None:
        conftest = tmp_path / "conftest.py"
        conftest.write_text(
            "import pytest\nfrom myapp import Settings\n\n\n"
            "@pytest.fixture\ndef drain():\n"
            '    return Settings().services["drain"]\n'
        )
        test_file = tmp_path / "test_drain.py"
        source = (
            "def test_Drain_RunsAsUser(drain):\n"
            '    assert drain["user"] == "1000:1000"\n'
        )
        test_file.write_text(source)

        assert list(check_file_literal_restatement(test_file, source)) == []

    def test_ProductionModule_NotChecked(self) -> None:
        source = (
            f"{_RESTATEMENT_HEADER}def test_Drain_RunsAsUser():\n"
            '    assert _compose()["user"] == "1000"\n'
        )
        assert list(check_file_literal_restatement(Path("src/x.py"), source)) == []


def _line_of(source: str, prefix: str) -> int:
    """Returns the 1-based line where `source` first opens with `prefix`."""
    lines = source.splitlines()
    return next(index for index, line in enumerate(lines, 1) if line.startswith(prefix))
