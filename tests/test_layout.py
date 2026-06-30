from pathlib import Path

import pytest

from repostyle.rules import (
    RS_ELEMENT_ORDER,
    check_class_member_order,
    check_module_element_order,
)


class TestCheckModuleElementOrder:
    @pytest.mark.parametrize(
        "source",
        [
            "def _helper():\n    return 1\n\n\ndef public():\n    return _helper()\n",
            "def _early():\n    return 1\n\n\ndef _late():\n    return _early()\n",
        ],
        ids=["helper_above_public_caller", "helper_above_helper_caller"],
    )
    def test_CalleeAboveItsCaller_FlagsViolation(
        self, tmp_path: Path, source: str
    ) -> None:
        target = _target(tmp_path, source)
        violations = list(check_module_element_order(target, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_ELEMENT_ORDER

    @pytest.mark.parametrize(
        "source",
        [
            "def _b():\n    return 1\n\n\ndef _a():\n    return 2\n",
            "class B:\n    pass\n\n\nclass A:\n    pass\n",
        ],
        ids=["private_helpers", "classes"],
    )
    def test_IndependentSiblingsOutOfAlphabeticalOrder_FlagsViolation(
        self, tmp_path: Path, source: str
    ) -> None:
        target = _target(tmp_path, source)
        violations = list(check_module_element_order(target, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_ELEMENT_ORDER

    def test_CalleeBelowItsCaller_NoViolation(self, tmp_path: Path) -> None:
        source = (
            "def public():\n    return _helper()\n\n\ndef _helper():\n    return 1\n"
        )
        target = _target(tmp_path, source)
        assert list(check_module_element_order(target, source)) == []

    def test_IndependentHelpersAlphabetical_NoViolation(self, tmp_path: Path) -> None:
        source = "def _a():\n    return 1\n\n\ndef _b():\n    return 2\n"
        target = _target(tmp_path, source)
        assert list(check_module_element_order(target, source)) == []

    @pytest.mark.parametrize(
        "source",
        [
            "def zebra():\n    return 1\n\n\ndef alpha():\n    return 2\n",
            "ZED = 1\nABE = 2\n",
        ],
        ids=["public_functions", "module_constants"],
    )
    def test_KindLeftToTheAuthor_NoViolation(self, tmp_path: Path, source: str) -> None:
        target = _target(tmp_path, source)
        assert list(check_module_element_order(target, source)) == []

    def test_BaseClassAboveSubclass_NoViolation(self, tmp_path: Path) -> None:
        # A base class must precede its subclass at definition time, so
        # the top-down order leaves it above and does not flag it.
        source = "class _Base:\n    pass\n\n\nclass Sub(_Base):\n    pass\n"
        target = _target(tmp_path, source)
        assert list(check_module_element_order(target, source)) == []

    def test_FieldAnnotationReferencesClassAbove_NoViolation(
        self, tmp_path: Path
    ) -> None:
        # A field's type annotation is evaluated when the class body
        # runs, so the annotated class must precede it; the top-down
        # order leaves it above and does not flag it.
        source = (
            "import dataclasses\n\n\n"
            "@dataclasses.dataclass\n"
            "class _Part:\n    x: int\n\n\n"
            "@dataclasses.dataclass\n"
            "class Whole:\n    part: _Part\n"
        )
        target = _target(tmp_path, source)
        assert list(check_module_element_order(target, source)) == []

    def test_AttributeDefaultInstantiatesClassAbove_NoViolation(
        self, tmp_path: Path
    ) -> None:
        # An attribute default runs at class-definition time, so the
        # instantiated class must precede the class that defaults to it.
        source = "class _Part:\n    pass\n\n\nclass Whole:\n    part: _Part = _Part()\n"
        target = _target(tmp_path, source)
        assert list(check_module_element_order(target, source)) == []

    @pytest.mark.parametrize(
        "source",
        [
            "class _Result:\n    pass\n\n\n"
            "def build() -> _Result:\n    return _Result()\n",
            "class _Arg:\n    pass\n\n\ndef consume(value: _Arg) -> None:\n    pass\n",
            "from typing import Protocol\n\n\n"
            "class _Started(Protocol):\n    def tick(self) -> float: ...\n\n\n"
            "class Clock(Protocol):\n    def __call__(self) -> _Started: ...\n",
        ],
        ids=["return_annotation", "param_annotation", "protocol_method_return"],
    )
    def test_SignatureAnnotationReferencesClassAbove_NoViolation(
        self, tmp_path: Path, source: str
    ) -> None:
        # A parameter or return annotation is evaluated when the `def`
        # runs, so the annotated class must precede it; the top-down
        # order leaves it above and does not flag it.
        target = _target(tmp_path, source)
        assert list(check_module_element_order(target, source)) == []

    def test_MethodBodyUsesHelperBelow_FlagsViolation(self, tmp_path: Path) -> None:
        # A method body defers to call time, so a helper it reads is a
        # top-down dependency: with the callee above its caller, the
        # class should move above the helper.
        source = (
            "def _helper():\n    return 1\n\n\n"
            "class K:\n    def run(self):\n        return _helper()\n"
        )
        target = _target(tmp_path, source)
        violations = list(check_module_element_order(target, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_ELEMENT_ORDER

    def test_ConstantConsumedByFunctionBelow_NoViolation(self, tmp_path: Path) -> None:
        # Constants stay at the head of the file regardless of what
        # reads them, so a function using one from below is not a
        # violation.
        source = "CONST = 1\n\n\ndef public():\n    return CONST\n"
        target = _target(tmp_path, source)
        assert list(check_module_element_order(target, source)) == []

    def test_PytestClassesNotAlphabetised_NoViolation(self, tmp_path: Path) -> None:
        # Test classes mirror the order of the callables they cover, not
        # an alphabetical one, so two out of order do not flag.
        source = "class TestB:\n    pass\n\n\nclass TestA:\n    pass\n"
        target = _target(tmp_path, source)
        assert list(check_module_element_order(target, source)) == []

    def test_LocalNameShadowingADefinition_NoViolation(self, tmp_path: Path) -> None:
        # The local '_helper' is not a reference to the helper below it,
        # so no dependency edge exists.
        source = (
            "def public():\n    _helper = 1\n    return _helper\n\n\n"
            "def _helper():\n    return 2\n"
        )
        target = _target(tmp_path, source)
        assert list(check_module_element_order(target, source)) == []

    def test_MutualRecursionCycle_NoViolation(self, tmp_path: Path) -> None:
        source = "def _a(n):\n    return _b(n)\n\n\ndef _b(n):\n    return _a(n)\n"
        target = _target(tmp_path, source)
        assert list(check_module_element_order(target, source)) == []

    def test_BranchingCycleAmongHelpers_NoViolation(self, tmp_path: Path) -> None:
        # All four helpers belong to one dependency cycle, so none is
        # independent of the others and alphabetical order does not
        # apply.
        source = (
            "def _a():\n    return _b() + _c()\n\n\n"
            "def _b():\n    return _d()\n\n\n"
            "def _c():\n    return _d()\n\n\n"
            "def _d():\n    return _a()\n"
        )
        target = _target(tmp_path, source)
        assert list(check_module_element_order(target, source)) == []

    def test_SyntaxError_NoViolation(self, tmp_path: Path) -> None:
        source = "def broken(\n"
        target = _target(tmp_path, source)
        assert list(check_module_element_order(target, source)) == []


class TestCheckClassMemberOrder:
    @pytest.mark.parametrize(
        "source",
        [
            "class K:\n    def _helper(self):\n        return 1\n\n"
            "    def run(self):\n        return 2\n",
            "class K:\n    def zebra(self):\n        return 1\n\n"
            "    def alpha(self):\n        return 2\n",
        ],
        ids=["private_before_public", "public_methods_unsorted"],
    )
    def test_MethodOutOfOrder_FlagsViolation(self, tmp_path: Path, source: str) -> None:
        target = _target(tmp_path, source)
        violations = list(check_class_member_order(target, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_ELEMENT_ORDER

    def test_EnumWithExplicitValuesOutOfOrder_FlagsViolation(
        self, tmp_path: Path
    ) -> None:
        source = "import enum\n\n\nclass E(enum.Enum):\n    B = 'b'\n    A = 'a'\n"
        target = _target(tmp_path, source)
        violations = list(check_class_member_order(target, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_ELEMENT_ORDER

    def test_PytestClassMethodsNotOrdered_NoViolation(self, tmp_path: Path) -> None:
        # A pytest test class follows scenario order, not the method
        # bands, so out-of-order test methods do not flag.
        source = (
            "class TestThing:\n"
            "    def test_zebra(self):\n        assert True\n\n"
            "    def test_alpha(self):\n        assert True\n"
        )
        target = _target(tmp_path, source)
        assert list(check_class_member_order(target, source)) == []

    def test_ConventionalLayout_NoViolation(self, tmp_path: Path) -> None:
        source = (
            "class K:\n"
            "    def __init__(self):\n        self.x = 1\n\n"
            "    def alpha(self):\n        return 1\n\n"
            "    def zebra(self):\n        return 2\n\n"
            "    def _helper(self):\n        return 3\n"
        )
        target = _target(tmp_path, source)
        assert list(check_class_member_order(target, source)) == []

    def test_AlphabeticalEnumWithExplicitValues_NoViolation(
        self, tmp_path: Path
    ) -> None:
        source = "import enum\n\n\nclass E(enum.Enum):\n    A = 'a'\n    B = 'b'\n"
        target = _target(tmp_path, source)
        assert list(check_class_member_order(target, source)) == []

    def test_EnumWithComputedValues_NoViolation(self, tmp_path: Path) -> None:
        source = (
            "from enum import Enum, auto\n\n\n"
            "class E(Enum):\n    B = auto()\n    A = auto()\n"
        )
        target = _target(tmp_path, source)
        assert list(check_class_member_order(target, source)) == []


def _target(tmp_path: Path, source: str, name: str = "m.py") -> Path:
    target = tmp_path / name
    target.write_text(source, encoding="utf-8")
    return target
