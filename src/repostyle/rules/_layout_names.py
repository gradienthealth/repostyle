"""Focused helpers extracted from a larger module."""

from __future__ import annotations

import ast

from repostyle._shared import TEST_CLASS_PATTERN


def is_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def is_test_class(node: ast.ClassDef) -> bool:
    """Reports whether a class is a pytest test class, collected by name."""
    return TEST_CLASS_PATTERN.match(node.name) is not None
