from pathlib import Path

import pytest

from gradient_pystyle.rules import (
    RS_ELEMENT_ORDER,
    check_class_member_order,
    check_module_element_order,
)


def _target(tmp_path: Path, source: str, config: str = "", name: str = "m.py") -> Path:
    if config:
        (tmp_path / "pyproject.toml").write_text(config, encoding="utf-8")
    target = tmp_path / name
    target.write_text(source, encoding="utf-8")
    return target


class TestCheckModuleElementOrder:
    @pytest.mark.parametrize(
        "source",
        [
            "def public():\n    return 1\n\n\nLIMIT = 10\n",
            "import os\n\n__all__ = ['os']\n",
            "def public():\n    return 1\n\n\ndef _helper():\n    return 2\n",
            "CONST = 1\n\n\nimport os\n",
        ],
        ids=[
            "constant_after_function",
            "dunder_after_import",
            "private_after_public",
            "import_after_constant",
        ],
    )
    def test_ElementBelowItsCategory_FlagsViolation(
        self, tmp_path: Path, source: str
    ) -> None:
        target = _target(tmp_path, source)
        violations = list(check_module_element_order(target, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_ELEMENT_ORDER

    def test_HelpersFirstLayout_NoViolation(self, tmp_path: Path) -> None:
        source = (
            '"""Module."""\n\nfrom __future__ import annotations\n\n'
            "import os\n\nLIMIT = 10\n\n\n"
            "def _helper():\n    return os\n\n\ndef public():\n    return _helper()\n"
        )
        target = _target(tmp_path, source)
        assert list(check_module_element_order(target, source)) == []

    @pytest.mark.parametrize(
        "source",
        [
            "def compute():\n    return 1\n\n\nRESULT = compute()\n",
            "BASE = object\n\n\ndef other():\n    return 1\n\n\n"
            "class Public(BASE):\n    pass\n",
        ],
        ids=["constant_reads_definition_above", "base_class_precedes_subclass"],
    )
    def test_DefinitionTimeDependencyForcesPosition_NoViolation(
        self, tmp_path: Path, source: str
    ) -> None:
        target = _target(tmp_path, source)
        assert list(check_module_element_order(target, source)) == []

    @pytest.mark.parametrize(
        "source",
        [
            "from typing import TYPE_CHECKING\n\n"
            "if TYPE_CHECKING:\n    from os import getcwd\n\nCONST = 1\n",
            "try:\n    import ujson as json\nexcept ImportError:\n    import json\n\n"
            "CONST = 1\n",
        ],
        ids=["type_checking_block", "try_except_import"],
    )
    def test_OpaqueGuardBlock_NoViolation(self, tmp_path: Path, source: str) -> None:
        target = _target(tmp_path, source)
        assert list(check_module_element_order(target, source)) == []

    def test_ConfiguredOrderOverridesDefault_FlagsAgainstConfig(
        self, tmp_path: Path
    ) -> None:
        # Public-first config: a helpers-first file now reads as out of
        # order.
        config = '[tool.gradient-pystyle]\nmodule-order = ["public", "private"]\n'
        source = "def _helper():\n    return 1\n\n\ndef public():\n    return 2\n"
        target = _target(tmp_path, source, config=config)
        violations = list(check_module_element_order(target, source))
        assert len(violations) == 1

    def test_EmptyOrderDisablesScope_NoViolation(self, tmp_path: Path) -> None:
        config = "[tool.gradient-pystyle]\nmodule-order = []\n"
        source = "def public():\n    return 1\n\n\nLIMIT = 10\n"
        target = _target(tmp_path, source, config=config)
        assert list(check_module_element_order(target, source)) == []

    def test_SyntaxError_NoViolation(self, tmp_path: Path) -> None:
        source = "def broken(\n"
        target = _target(tmp_path, source)
        assert list(check_module_element_order(target, source)) == []


class TestCheckClassMemberOrder:
    @pytest.mark.parametrize(
        "source",
        [
            "class C:\n    def run(self):\n        return 1\n\n"
            "    def __init__(self):\n        self.x = 1\n",
            "class C:\n    def run(self):\n        return 1\n\n    field: int = 0\n",
            "class C:\n    def _helper(self):\n        return 1\n\n"
            "    def run(self):\n        return 2\n",
        ],
        ids=[
            "constructor_after_method",
            "field_after_method",
            "private_method_before_public_method",
        ],
    )
    def test_MemberBelowItsCategory_FlagsViolation(
        self, tmp_path: Path, source: str
    ) -> None:
        target = _target(tmp_path, source)
        violations = list(check_class_member_order(target, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_ELEMENT_ORDER

    def test_ConventionalLayout_NoViolation(self, tmp_path: Path) -> None:
        source = (
            "class C:\n"
            '    """Doc."""\n\n'
            "    field: int = 0\n\n"
            "    def __init__(self):\n        self.value = 1\n\n"
            "    def run(self):\n        return self._helper()\n\n"
            "    def _helper(self):\n        return self.value\n"
        )
        target = _target(tmp_path, source)
        assert list(check_class_member_order(target, source)) == []

    def test_PropertyAndSetterCluster_NoViolation(self, tmp_path: Path) -> None:
        source = (
            "class C:\n"
            "    @property\n    def value(self):\n        return self._value\n\n"
            "    @value.setter\n    def value(self, new):\n        self._value = new\n"
        )
        target = _target(tmp_path, source)
        assert list(check_class_member_order(target, source)) == []

    def test_NestedClassBody_IsChecked(self, tmp_path: Path) -> None:
        source = (
            "class Outer:\n"
            "    class Inner:\n"
            "        def run(self):\n            return 1\n\n"
            "        def __init__(self):\n            self.x = 1\n"
        )
        target = _target(tmp_path, source)
        violations = list(check_class_member_order(target, source))
        assert len(violations) == 1

    def test_EmptyClassOrderDisablesScope_NoViolation(self, tmp_path: Path) -> None:
        config = "[tool.gradient-pystyle]\nclass-order = []\n"
        source = (
            "class C:\n    def run(self):\n        return 1\n\n"
            "    def __init__(self):\n        self.x = 1\n"
        )
        target = _target(tmp_path, source, config=config)
        assert list(check_class_member_order(target, source)) == []
