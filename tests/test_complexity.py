from pathlib import Path

from repostyle.rules import RS_COGNITIVE_COMPLEXITY, check_cognitive_complexity

_COMPLEX_SOURCE = (
    "def handle(items):\n"
    "    for item in items:\n"
    "        if item:\n"
    "            while item.next:\n"
    "                if item.ok and item.ready:\n"
    "                    for value in item:\n"
    "                        if value:\n"
    "                            return value\n"
)


class TestCheckCognitiveComplexity:
    def test_DeeplyNestedFunction_FlagsViolation(self) -> None:
        violations = list(check_cognitive_complexity(Path("src/x.py"), _COMPLEX_SOURCE))
        assert len(violations) == 1
        assert violations[0].rule == RS_COGNITIVE_COMPLEXITY
        assert "cognitive complexity" in violations[0].message

    def test_FlatFunction_NoViolation(self) -> None:
        source = (
            "def f(a, b):\n    if a:\n        return 1\n    if b:\n        return 2\n"
        )
        assert list(check_cognitive_complexity(Path("src/x.py"), source)) == []

    def test_NonPythonFile_NotChecked(self) -> None:
        result = check_cognitive_complexity(Path("README.md"), _COMPLEX_SOURCE)
        assert list(result) == []
