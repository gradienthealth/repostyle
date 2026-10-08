from pathlib import Path

import pytest

from repostyle.rules import (
    RS_CONDITIONAL_TEST_LOGIC,
    RS_NO_MOCK_PATCH,
    RS_SLEEPY_TEST,
    RS_TEST_NAMING,
    check_java_conditional_test_logic,
    check_java_no_mock_library,
    check_java_sleepy_test,
    check_java_test_naming,
)

_TEST_PATH = Path("src/test/java/io/example/WidgetTest.java")


class TestJavaTestNaming:
    @pytest.mark.parametrize(
        "name",
        ["testEmptyQueue", "emptyQueue_returns_nothing", "EmptyQueue_returnsNothing"],
        ids=["no_underscore", "three_parts", "capitalized"],
    )
    def test_OffConventionName_IsFlagged(self, name: str) -> None:
        source = _test_class(f"@Test\n  void {name}() {{}}")
        assert _rules(check_java_test_naming(_TEST_PATH, source)) == [RS_TEST_NAMING]

    def test_ConventionalParameterizedTest_IsAccepted(self) -> None:
        source = _test_class(
            "@ParameterizedTest\n  @ValueSource(ints = {1})\n  void anyCount_isPositive(int n) {}"
        )
        assert list(check_java_test_naming(_TEST_PATH, source)) == []

    def test_HelperMethod_IsNotATest(self) -> None:
        source = _test_class("private Widget buildWidget() { return new Widget(); }")
        assert list(check_java_test_naming(_TEST_PATH, source)) == []

    def test_MainSourceMethod_IsNotATest(self) -> None:
        source = _test_class("@Test\n  void testEmptyQueue() {}")
        main_path = Path("src/main/java/io/example/Widget.java")
        assert list(check_java_test_naming(main_path, source)) == []


class TestJavaNoMockLibrary:
    @pytest.mark.parametrize(
        "line",
        ["import org.mockito.Mockito;", "import static org.mockito.Mockito.when;"],
        ids=["class", "static"],
    )
    def test_MockitoImport_IsFlagged(self, line: str) -> None:
        source = f"{line}\n\nclass WidgetTest {{}}\n"
        assert _rules(check_java_no_mock_library(_TEST_PATH, source)) == [
            RS_NO_MOCK_PATCH
        ]

    def test_LookalikePackage_IsAccepted(self) -> None:
        source = "import org.mockitoish.Thing;\n\nclass WidgetTest {}\n"
        assert list(check_java_no_mock_library(_TEST_PATH, source)) == []


class TestJavaConditionalTestLogic:
    @pytest.mark.parametrize(
        "body",
        [
            "if (ready) {\n      assertTrue(ok);\n    }",
            "for (int i : items) assertEquals(1, i);",
            "try {\n      run();\n      fail();\n    } catch (IOException e) {\n      assertEquals(1, 1);\n    }",
        ],
        ids=["if_block", "unbraced_loop", "try_catch"],
    )
    def test_AssertionInControlFlow_IsFlagged(self, body: str) -> None:
        source = _test_class(f"@Test\n  void ready_passes() {{\n    {body}\n  }}")
        assert RS_CONDITIONAL_TEST_LOGIC in _rules(
            check_java_conditional_test_logic(_TEST_PATH, source)
        )

    @pytest.mark.parametrize(
        "body",
        [
            "try (Scu scu = open()) {\n      assertEquals(0, scu.store());\n    }",
            "if (ready) {\n      run();\n    }\n    assertTrue(ok);",
            "assertThrows(IOException.class, () -> {\n      if (x) { run(); }\n    });",
        ],
        ids=["try_with_resources", "assertion_after_branch", "lambda_branch"],
    )
    def test_StraightLineAssertion_IsAccepted(self, body: str) -> None:
        source = _test_class(f"@Test\n  void ready_passes() {{\n    {body}\n  }}")
        assert list(check_java_conditional_test_logic(_TEST_PATH, source)) == []


class TestJavaSleepyTest:
    @pytest.mark.parametrize(
        "call",
        ["Thread.sleep(100);", "TimeUnit.MILLISECONDS.sleep(100);"],
        ids=["thread", "time_unit"],
    )
    def test_RealSleep_IsFlagged(self, call: str) -> None:
        source = _test_class(
            f"@Test\n  void pause_waits() throws Exception {{\n    {call}\n  }}"
        )
        assert _rules(check_java_sleepy_test(_TEST_PATH, source)) == [RS_SLEEPY_TEST]

    def test_ZeroSleep_IsAccepted(self) -> None:
        source = _test_class(
            "@Test\n  void pause_yields() throws Exception {\n    Thread.sleep(0);\n  }"
        )
        assert list(check_java_sleepy_test(_TEST_PATH, source)) == []


def _rules(violations: object) -> list[str]:
    return [violation.rule for violation in violations]


def _test_class(members: str) -> str:
    return f"class WidgetTest {{\n  {members}\n}}\n"
