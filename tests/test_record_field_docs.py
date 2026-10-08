from pathlib import Path

import pytest

from repostyle.rules import (
    RS_FIELD_DESCRIBED_IN_CLASS_DOCSTRING,
    check_field_described_in_class_docstring,
)

_SRC = Path("src/x.py")


class TestCheckFieldDescribedInClassDocstring:
    @pytest.mark.parametrize(
        "header",
        [
            "@dataclass\nclass Verdict:\n",
            "@dataclasses.dataclass(frozen=True)\nclass Verdict:\n",
            "@attrs.define\nclass Verdict:\n",
            "@attr.s(auto_attribs=True)\nclass Verdict:\n",
            "class Verdict(NamedTuple):\n",
            "class Verdict(typing.TypedDict):\n",
            "class Verdict(BaseModel):\n",
        ],
        ids=[
            "dataclass",
            "dataclass-call",
            "attrs-define",
            "attr-s",
            "named-tuple",
            "typed-dict",
            "pydantic",
        ],
    )
    def test_RecordFieldNarratedAsSubject_FlagsField(self, header: str) -> None:
        source = (
            header + '    """A stage verdict.\n'
            "\n"
            "    The `skip_reason` says why the series was skipped.\n"
            '    """\n'
            "\n"
            "    skip_reason: str | None\n"
        )

        violations = _check(source)

        assert [v.rule for v in violations] == [RS_FIELD_DESCRIBED_IN_CLASS_DOCSTRING]
        assert "'skip_reason'" in violations[0].message

    def test_FieldsNarratedInCoordinatedClauses_FlagsEach(self) -> None:
        source = (
            "@dataclass\n"
            "class Verdict:\n"
            '    """A stage verdict.\n'
            "\n"
            "    Either the series was defaced, and `instances` holds one result\n"
            "    per instance, or it was skipped, and `skip_reason` says why.\n"
            '    """\n'
            "\n"
            "    skip_reason: str | None\n"
            "    instances: dict[str, float] | None\n"
        )

        assert _flagged(source) == ["skip_reason", "instances"]

    def test_FieldsNarratedAsCompoundSubject_FlagsEach(self) -> None:
        source = (
            "@dataclass\n"
            "class Verdict:\n"
            '    """A stage verdict.\n'
            "\n"
            "    `skip_reason` and `instances` come from the stage's last run.\n"
            '    """\n'
            "\n"
            "    skip_reason: str | None\n"
            "    instances: dict[str, float] | None\n"
        )

        assert _flagged(source) == ["skip_reason", "instances"]

    def test_FieldListedUnderArgs_FlagsField(self) -> None:
        source = (
            "@dataclass\n"
            "class Verdict:\n"
            '    """A stage verdict.\n'
            "\n"
            "    Args:\n"
            "        skip_reason: Why the series was skipped.\n"
            '    """\n'
            "\n"
            "    skip_reason: str | None\n"
        )

        assert _flagged(source) == ["skip_reason"]

    def test_FieldWithItsOwnDocstring_NoViolation(self) -> None:
        source = (
            "@dataclass\n"
            "class Verdict:\n"
            '    """A stage verdict.\n'
            "\n"
            "    The `skip_reason` says why the series was skipped.\n"
            '    """\n'
            "\n"
            "    skip_reason: str | None\n"
            '    """Why the series was skipped, or `None`."""\n'
        )

        assert _check(source) == []

    @pytest.mark.parametrize(
        "prose",
        [
            "Publishes the `skip_reason` beside the per-instance scores.",
            "Carries `head_count`, `face_count`, and `skip_reason`.",
            "Combines `head_count`, `face_count`, and `skip_reason` into a row.",
            "The `head_count`, `face_count`, and `skip_reason` values are counts.",
            "Accepts `head_count`, or `skip_reason` when no head is found.",
            "The `SKIP_REASON` is unrelated.",
        ],
        ids=[
            "object-reference",
            "list-tail",
            "list-tail-continues",
            "list-modifier",
            "coordinated-object",
            "different-case",
        ],
    )
    def test_FieldOnlyReferenced_NoViolation(self, prose: str) -> None:
        source = (
            "@dataclass\n"
            "class Verdict:\n"
            f'    """A stage verdict.\n\n    {prose}\n    """\n'
            "\n"
            "    skip_reason: str | None\n"
        )

        assert _check(source) == []

    @pytest.mark.parametrize(
        "source",
        [
            "class Verdict:\n"
            '    """A stage verdict.\n\n    The `skip_reason` says why.\n    """\n'
            "\n"
            "    skip_reason: str | None\n",
            "@dataclass\n"
            "class Verdict:\n"
            '    """A stage verdict.\n\n    The `limit` caps every series.\n    """\n'
            "\n"
            "    limit: ClassVar[int] = 3\n",
            "@dataclass\n"
            "class Verdict:\n"
            '    """A stage verdict.\n\n    The `limit` caps every series.\n    """\n'
            "\n"
            '    limit: "ClassVar[int]" = 3\n',
            "@dataclass\n"
            "class Verdict:\n"
            '    """A stage verdict.\n\n    Args:\n        seed: The random seed.\n    """\n'
            "\n"
            "    seed: InitVar[int]\n",
        ],
        ids=["plain-class", "class-var", "string-class-var", "init-var"],
    )
    def test_NotARecordField_NoViolation(self, source: str) -> None:
        assert _check(source) == []


def _flagged(source: str) -> list[str]:
    return [v.message.split("'")[1] for v in _check(source)]


def _check(source: str, path: Path = _SRC) -> list:
    return list(check_field_described_in_class_docstring(path, source))
