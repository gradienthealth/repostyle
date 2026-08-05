from pathlib import Path

import pytest

from repostyle.rules import RS_OVER_BROAD_EXCEPT, Violation, check_over_broad_except

_SRC = Path("src/x.py")


class TestCheckOverBroadExcept:
    @pytest.mark.parametrize(
        "source",
        [
            pytest.param(
                "try:\n    f()\nexcept (AttributeError, TypeError):\n    pass\n",
                id="two-structural-builtins",
            ),
            pytest.param(
                "try:\n"
                "    f()\n"
                "except (KeyError, AttributeError, TypeError, ValueError):\n"
                "    pass\n",
                id="three-structural-builtins-among-others",
            ),
            pytest.param(
                "try:\n"
                "    f()\n"
                "except (TruRezError, AttributeError, TypeError, KeyError):\n"
                "    pass\n",
                id="project-exception-with-structural-builtins",
            ),
            pytest.param(
                "try:\n    f()\nexcept (ParseError, KeyError):\n    pass\n",
                id="project-exception-with-one-structural-builtin",
            ),
            pytest.param(
                "try:\n    f()\nexcept (errors.ParseError, KeyError):\n    pass\n",
                id="qualified-project-exception",
            ),
            pytest.param(
                "try:\n    f()\nexcept (TypeError, TypeError, KeyError):\n    pass\n",
                id="repeated-builtin-counted-once-still-reaches-two",
            ),
        ],
    )
    def test_WideHandler_FlagsViolation(self, source: str) -> None:
        violations = _check(source)
        assert len(violations) == 1
        assert violations[0].rule == RS_OVER_BROAD_EXCEPT

    def test_MixedHandler_NamesBothSides(self) -> None:
        source = "try:\n    f()\nexcept (ParseError, KeyError):\n    pass\n"
        assert "KeyError" in _check(source)[0].message
        assert "ParseError" in _check(source)[0].message

    def test_BuiltinOnlyHandler_PointsAtWhereToRaiseInstead(self) -> None:
        source = "try:\n    f()\nexcept (AttributeError, KeyError):\n    pass\n"
        assert "raise a named error" in _check(source)[0].message

    def test_WideHandler_ListsBuiltinsInSourceOrder(self) -> None:
        source = "try:\n    f()\nexcept (TypeError, AttributeError):\n    pass\n"
        assert "TypeError, AttributeError" in _check(source)[0].message

    def test_WideHandler_ReportsTheExceptLine(self) -> None:
        source = "try:\n    f()\nexcept (AttributeError, TypeError):\n    pass\n"
        assert _check(source)[0].line == 3

    @pytest.mark.parametrize(
        "source",
        [
            pytest.param(
                "try:\n    f()\nexcept (TypeError, ValueError):\n    pass\n",
                id="the-int-conversion-pair",
            ),
            pytest.param(
                "try:\n    f()\nexcept AttributeError:\n    pass\n",
                id="one-structural-builtin-alone",
            ),
            pytest.param(
                "try:\n    f()\nexcept (KeyError, KeyError):\n    pass\n",
                id="one-structural-builtin-repeated-is-still-one",
            ),
            pytest.param(
                "try:\n    f()\nexcept (ParseError, OSError):\n    pass\n",
                id="project-exception-with-an-environment-error",
            ),
            pytest.param(
                "try:\n    f()\nexcept (ValueError, OSError, RuntimeError):\n    pass\n",
                id="three-non-structural-builtins",
            ),
            pytest.param(
                "try:\n    f()\nexcept Exception:\n    pass\n",
                id="bare-exception-belongs-to-ruff",
            ),
            pytest.param(
                "try:\n    f()\nexcept:\n    pass\n",
                id="bare-except-belongs-to-ruff",
            ),
            pytest.param(
                "try:\n    f()\nexcept (ParseError, ScanError):\n    pass\n",
                id="two-project-exceptions",
            ),
            pytest.param(
                "try:\n"
                "    f()\n"
                "except (KeyError, TypeError) as exc:\n"
                "    raise ParseError('missing field') from exc\n",
                id="converting-boundary-re-raises",
            ),
            pytest.param(
                "try:\n"
                "    f()\n"
                "except (KeyError, TypeError) as exc:\n"
                "    logger.warning('malformed')\n"
                "    raise ParseError('missing field') from exc\n",
                id="converting-boundary-logs-then-raises",
            ),
        ],
    )
    def test_NarrowHandler_IsLeftAlone(self, source: str) -> None:
        assert not _check(source)

    def test_HandlerRaisingOnOneBranchOnly_StillFlagsViolation(self) -> None:
        source = (
            "try:\n"
            "    f()\n"
            "except (KeyError, TypeError):\n"
            "    if strict:\n"
            "        raise\n"
            "    return None\n"
        )
        assert len(_check(source)) == 1

    def test_NonPythonFile_NotChecked(self) -> None:
        source = "try:\n    f()\nexcept (AttributeError, TypeError):\n    pass\n"
        assert not _check(source, Path("README.md"))

    def test_UnparsableSource_YieldsNothing(self) -> None:
        assert not _check("def (\n")


def _check(source: str, path: Path = _SRC) -> list[Violation]:
    return list(check_over_broad_except(path, source))
