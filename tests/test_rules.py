import sys
from pathlib import Path

import pytest

from pystyle.rules import (
    RS_ACRONYM_CASING,
    RS_BANNED_ABBREVIATION,
    RS_BEHAVIOR_VERIFICATION_ONLY,
    RS_BOOLEAN_PREFIX_REQUIRED,
    RS_CONDITIONAL_TEST_LOGIC,
    RS_DISCOURAGED_CLASS_SUFFIX,
    RS_DOC_FILL,
    RS_DURATION_AS_TIMEDELTA,
    RS_EXCEPTION_ALIAS,
    RS_EXCESSIVE_MOCKING,
    RS_NO_ATTRIBUTES_BLOCK,
    RS_NO_DOUBLE_BACKTICKS,
    RS_NO_MAKE_IN_PRODUCTION,
    RS_NO_MOCK_PATCH,
    RS_NO_NEGATED_BOOLEAN,
    RS_NO_PHI_SAFE_EXC_INFO,
    RS_PORT_NO_IMPLEMENTATION,
    RS_SLEEPY_TEST,
    RS_TEST_NAMING,
    check_acronym_casing,
    check_banned_abbreviation,
    check_behavior_verification_only,
    check_boolean_prefix_required,
    check_conditional_test_logic,
    check_discouraged_class_suffix,
    check_doc_fill,
    check_duration_as_timedelta,
    check_exception_alias,
    check_excessive_mocking,
    check_no_attributes_block,
    check_no_double_backticks_in_docstrings,
    check_no_double_backticks_in_md,
    check_no_make_in_production,
    check_no_mock_patch,
    check_no_negated_boolean,
    check_no_phi_safe_with_exc_info,
    check_port_no_implementation,
    check_sleepy_test,
    check_test_naming,
)

# PEP 695 type-alias / type-parameter syntax only parses on Python
# 3.12+, so these cases skip on 3.11, where the source is a SyntaxError
# the checker correctly cannot inspect (such code cannot exist on 3.11
# anyway).
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


class TestCheckAcronymCasing:
    @pytest.mark.parametrize(
        ("source", "acronym"),
        [
            ("class FhirClient: ...", "FHIR"),
            ("class ClientFhir: ...", "FHIR"),
            ("class JwtSigner: ...", "JWT"),
            ("class JsonHTTPError: ...", "JSON"),
            ("class HttpRetry: ...", "HTTP"),
            ("class PatientId: ...", "ID"),
            ("T = TypeVar('FhirT')", "FHIR"),
            ("T = typing.TypeVar('FhirT')", "FHIR"),
            pytest.param("type FhirAlias = int", "FHIR", marks=_REQUIRES_PEP695),
            pytest.param("class Container[FhirT]: ...", "FHIR", marks=_REQUIRES_PEP695),
            pytest.param(
                "def fn[FhirT]() -> None: ...", "FHIR", marks=_REQUIRES_PEP695
            ),
        ],
    )
    def test_LowercaseAcronym_FlagsViolation(self, source: str, acronym: str) -> None:
        violations = list(check_acronym_casing(Path("src/x.py"), source))
        assert len(violations) == 1
        assert violations[0].rule == RS_ACRONYM_CASING
        assert acronym in violations[0].message

    def test_IndentedDeclaration_ColumnPointsAtDeclaration(self) -> None:
        source = "if True:\n    class FhirClient: ...\n"
        violations = list(check_acronym_casing(Path("src/x.py"), source))
        assert (violations[0].line, violations[0].col) == (2, 5)

    @pytest.mark.parametrize(
        "source",
        [
            "class FHIRClient: ...",
            "class JWTSigner: ...",
            "class EpicFHIRClient: ...",
            "class _Internal: ...",
            "TToken = TypeVar('TToken')",
            "TToken = typing.TypeVar('TToken')",
            "patient_id = 1",
            "class API: ...",
            pytest.param("type FHIRAlias = int", marks=_REQUIRES_PEP695),
            pytest.param("class Container[FHIRT]: ...", marks=_REQUIRES_PEP695),
            "class TestDeidentifyBundle: ...",
            "class Identifier: ...",
            "class TestIdentityResolver: ...",
        ],
    )
    def test_ConformingIdentifier_NoViolation(self, source: str) -> None:
        assert list(check_acronym_casing(Path("src/x.py"), source)) == []

    def test_NonPythonFile_NotChecked(self) -> None:
        assert list(check_acronym_casing(Path("README.md"), "class FhirClient")) == []


class TestCheckTestNaming:
    @pytest.mark.parametrize(
        "name",
        [
            "test_empty_bundle_returns_empty_list",
            "test_EmptyBundle",
            "test_emptybundle_ReturnsEmptyList",
            "test_EmptyBundle_returnsEmptyList",
        ],
    )
    def test_NonConformingName_FlagsViolation(self, name: str) -> None:
        source = f"def {name}(): ..."
        violations = list(check_test_naming(Path("tests/unit/test_x.py"), source))
        assert len(violations) == 1
        assert violations[0].rule == RS_TEST_NAMING

    @pytest.mark.parametrize(
        "name",
        [
            "test_EmptyBundle_ReturnsEmptyList",
            "test_AcronymID_StaysUppercase",
            "test_X_Y",
        ],
    )
    def test_ConformingName_NoViolation(self, name: str) -> None:
        source = f"def {name}(): ..."
        path = Path("tests/unit/test_x.py")
        assert list(check_test_naming(path, source)) == []

    def test_NonTestFunction_NotChecked(self) -> None:
        source = "def helper_function(): ..."
        assert list(check_test_naming(Path("tests/unit/test_x.py"), source)) == []

    def test_OutsideTestsUnit_NotChecked(self) -> None:
        source = "def test_bad_name(): ..."
        assert list(check_test_naming(Path("src/x.py"), source)) == []

    def test_Conftest_NotChecked(self) -> None:
        source = "def test_bad_name(): ..."
        assert list(check_test_naming(Path("tests/unit/conftest.py"), source)) == []


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
        violations = list(check_no_mock_patch(Path("tests/unit/test_x.py"), source))
        assert len(violations) == 1
        assert violations[0].rule == RS_NO_MOCK_PATCH

    def test_FromUnittestImportMock_FlagsViolation(self) -> None:
        source = "from unittest import mock"
        violations = list(check_no_mock_patch(Path("tests/unit/test_x.py"), source))
        assert len(violations) == 1
        assert violations[0].rule == RS_NO_MOCK_PATCH

    def test_NonMockImport_NoViolation(self) -> None:
        source = "from collections import OrderedDict"
        assert list(check_no_mock_patch(Path("tests/unit/test_x.py"), source)) == []

    def test_InsideTestsFakes_NotChecked(self) -> None:
        source = "import unittest.mock"
        assert list(check_no_mock_patch(Path("tests/fakes/fake_x.py"), source)) == []


class TestCheckNoAttributesBlock:
    def test_AttributesBlockHeader_FlagsViolation(self) -> None:
        violations = list(
            check_no_attributes_block(Path("src/x.py"), _ATTRIBUTES_BLOCK_HEADER)
        )
        assert len(violations) == 1
        assert violations[0].rule == RS_NO_ATTRIBUTES_BLOCK

    def test_ModuleDocstring_ColumnFallsBackToOne(self) -> None:
        source = '"""Attributes:\n    name: full name.\n"""\n'
        violations = list(check_no_attributes_block(Path("src/x.py"), source))
        assert (violations[0].line, violations[0].col) == (1, 1)

    @pytest.mark.parametrize(
        "source",
        [_ATTRIBUTES_NO_BLOCK, _ATTRIBUTES_INLINE_PROSE],
        ids=["no-block", "inline-prose"],
    )
    def test_NoBlockHeader_NoViolation(self, source: str) -> None:
        assert list(check_no_attributes_block(Path("src/x.py"), source)) == []


class TestCheckNoDoubleBackticksInMd:
    def test_DoubleBackticksInProse_FlagsViolation(self) -> None:
        violations = list(
            check_no_double_backticks_in_md(
                Path("README.md"), "See ``ClassName`` for details."
            )
        )
        assert len(violations) == 1
        assert violations[0].rule == RS_NO_DOUBLE_BACKTICKS

    def test_DoubleBackticksMidLine_ColumnAtBacktickPair(self) -> None:
        violations = list(
            check_no_double_backticks_in_md(
                Path("README.md"), "See ``ClassName`` for details."
            )
        )
        assert (violations[0].line, violations[0].col) == (1, 5)

    @pytest.mark.parametrize(
        "source",
        [
            "See `ClassName` for details.",
            "```python\nx = 1\n```",
            "```python\n``not flagged``\n```",
        ],
        ids=["single", "fence-only", "double-inside-fence"],
    )
    def test_NoDoubleBackticksOutsideFences_NoViolation(self, source: str) -> None:
        assert list(check_no_double_backticks_in_md(Path("README.md"), source)) == []

    def test_NonMarkdownFile_NotChecked(self) -> None:
        assert (
            list(check_no_double_backticks_in_md(Path("README.txt"), "See ``X``."))
            == []
        )


class TestCheckNoDoubleBackticksInDocstrings:
    def test_DoubleBackticksInDocstring_FlagsViolation(self) -> None:
        violations = list(
            check_no_double_backticks_in_docstrings(
                Path("src/x.py"), '"""See ``ClassName`` for details."""'
            )
        )
        assert len(violations) == 1
        assert violations[0].rule == RS_NO_DOUBLE_BACKTICKS

    def test_SingleBackticksInDocstring_NoViolation(self) -> None:
        assert (
            list(
                check_no_double_backticks_in_docstrings(
                    Path("src/x.py"), '"""See `ClassName` for details."""'
                )
            )
            == []
        )


class TestCheckPortNoImplementation:
    @pytest.mark.parametrize(
        ("source", "token"),
        [
            ('"""Uses httpx under the hood."""', "httpx"),
            ('"""Backed by sqlalchemy AsyncSession."""', "sqlalchemy"),
            ('"""Writes to bigquery."""', "bigquery"),
            ('"""Uses psycopg as driver."""', "psycopg"),
        ],
    )
    def test_PortDocstringMentionsImpl_FlagsViolation(
        self, source: str, token: str
    ) -> None:
        path = Path("src/fhir_ingestor/application/ports/example.py")
        violations = list(check_port_no_implementation(path, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_PORT_NO_IMPLEMENTATION
        assert token in violations[0].message

    def test_PortDocstringContractOnly_NoViolation(self) -> None:
        source = '"""Yield a lease on a pending row for the duration of the context."""'
        path = Path("src/fhir_ingestor/application/ports/example.py")
        assert list(check_port_no_implementation(path, source)) == []

    def test_AdapterFileMentionsImpl_NotChecked(self) -> None:
        source = '"""Backed by sqlalchemy."""'
        path = Path("src/fhir_ingestor/infrastructure/adapters/example.py")
        assert list(check_port_no_implementation(path, source)) == []


class TestCheckDurationAsTimedelta:
    @pytest.mark.parametrize(
        "source",
        [
            "POLL_INTERVAL_SECONDS = 30",
            "_DEFAULT_ASSERTION_LIFETIME_SECONDS = 240",
            "RESTART_FLUSH_DELAY_SECONDS = 0.5",
            "REFRESH_SKEW_SECONDS: float = 30",
        ],
        ids=["public_int", "private_int", "public_float", "annotated"],
    )
    def test_ModuleLevelSecondsConstant_FlagsViolation(self, source: str) -> None:
        violations = list(check_duration_as_timedelta(Path("src/x.py"), source))
        assert len(violations) == 1
        assert violations[0].rule == RS_DURATION_AS_TIMEDELTA
        assert "timedelta(seconds=" in violations[0].message

    @pytest.mark.parametrize(
        "source",
        [
            "from datetime import timedelta\nPOLL_INTERVAL = timedelta(seconds=30)",
            "class Settings:\n    request_timeout_seconds: float = 60.0",
            "class Config:\n    poll_interval_seconds: float",
            "def f() -> int:\n    LOCAL_SECONDS = 5\n    return LOCAL_SECONDS",
            "EXPIRES_IN = 3600",
            "MAX_RETRIES_SECONDS_BETWEEN = 'documented'",
        ],
        ids=[
            "timedelta_constant",
            "settings_field",
            "domain_field",
            "local_variable",
            "name_without_seconds_suffix",
            "string_value",
        ],
    )
    def test_NotAModuleLevelSecondsLiteral_NoViolation(self, source: str) -> None:
        assert list(check_duration_as_timedelta(Path("src/x.py"), source)) == []


class TestCheckNoPHISafeWithExcInfo:
    @pytest.mark.parametrize(
        "source",
        [
            'logger.exception("boom", extra={"phi_safe": True})',
            'logger.error("boom", exc_info=True, extra={"phi_safe": True})',
            'logger.error("boom", exc_info=exc, extra={"phi_safe": True})',
            'logger.warning("boom", exc_info=True, extra={**fields, "phi_safe": True})',
            'logger.log(level, "boom", exc_info=True, extra={"phi_safe": True})',
            'logger.exception("boom", extra=dict(phi_safe=True))',
        ],
        ids=[
            "exception_method",
            "exc_info_true",
            "exc_info_variable",
            "dict_unpack_extra",
            "log_method",
            "dict_constructor_extra",
        ],
    )
    def test_ExcInfoRecordMarkedPHISafe_FlagsViolation(self, source: str) -> None:
        violations = list(check_no_phi_safe_with_exc_info(Path("src/x.py"), source))
        assert len(violations) == 1
        assert violations[0].rule == RS_NO_PHI_SAFE_EXC_INFO
        assert "exc_info" in violations[0].message

    @pytest.mark.parametrize(
        "source",
        [
            'logger.info("ready", extra={"phi_safe": True})',
            'logger.exception("boom")',
            'logger.exception("boom", extra={"event_type": "tick"})',
            'logger.error("boom", exc_info=False, extra={"phi_safe": True})',
            'logger.error("boom", exc_info=None, extra={"phi_safe": True})',
            'logger.error("boom", exc_info=True, extra=fields)',
            'logger.exception("boom", extra=dict(event_type="tick"))',
            'client.exception("boom")',
        ],
        ids=[
            "marked_without_exc_info",
            "exception_unmarked",
            "exception_other_extra",
            "exc_info_false",
            "exc_info_none",
            "non_literal_extra",
            "dict_constructor_other_extra",
            "non_logging_attribute",
        ],
    )
    def test_NoMarkedExcInfoCombination_NoViolation(self, source: str) -> None:
        assert list(check_no_phi_safe_with_exc_info(Path("src/x.py"), source)) == []


class TestCheckDocFill:
    @pytest.mark.parametrize(
        ("source", "fragment"),
        [
            (
                'def f():\n    """Summary.\n\n    aaa\n    bbb\n    """',
                "under-wrapped",
            ),
            (
                '"""Summary.\n\n' + "abcde " * 13 + 'end\n"""',
                "exceeds",
            ),
            (
                '"""Summary.\n\n`' + "word " * 16 + 'x\n"""',
                "exceeds",
            ),
            (
                'def f():\n    """Summary.\n\n'
                "    Args:\n        alpha: Word\n            more text.\n"
                '    """',
                "under-wrapped",
            ),
            (
                'def f():\n    """Summary.\n\n'
                "    Args:\n        alpha: Word.\n\n"
                "    aaa\n    bbb\n"
                '    """',
                "under-wrapped",
            ),
            (
                "# aaa\n# bbb\nx = 1",
                "under-wrapped",
            ),
            (
                "# " + "abcde " * 13 + "end\nx = 1",
                "exceeds",
            ),
            (
                "# aaa\n# bbb\n# type: ignore\nx = 1",
                "under-wrapped",
            ),
        ],
        ids=[
            "underwrapped_docstring",
            "overlong_docstring",
            "overlong_unbalanced_backtick",
            "underwrapped_args_continuation",
            "underwrapped_paragraph_after_args_block",
            "underwrapped_comment",
            "overlong_comment",
            "underwrapped_comment_before_directive",
        ],
    )
    def test_LooselyFilledParagraph_FlagsViolation(
        self, source: str, fragment: str
    ) -> None:
        violations = list(check_doc_fill(Path("src/x.py"), source))
        assert len(violations) == 1
        assert violations[0].rule == RS_DOC_FILL
        assert fragment in violations[0].message

    def test_IndentedDocstring_ColumnAtParagraphIndent(self) -> None:
        source = 'def f():\n    """Summary.\n\n    aaa\n    bbb\n    """'
        violations = list(check_doc_fill(Path("src/x.py"), source))
        assert (violations[0].line, violations[0].col) == (4, 5)

    @pytest.mark.parametrize(
        "source",
        [
            'def f():\n    """Summary.\n\n    ' + "a" * 64 + "\n    bbbb\n" + '    """',
            '"""' + "abcde " * 13 + 'end."""',
            '"""Summary line that runs well past the seventy-two column limit xxxx\n\n'
            'body.\n"""',
            'def f():\n    """Summary.\n\n'
            "    Args:\n        alpha: Short.\n        beta: Short.\n"
            '    """',
            '"""Summary.\n\n- aaa\n- bbb\n"""',
            '"""Slug.\n\nRevision ID: abc\nRevises: def\n"""',
            '"""Summary.\n\nSee https://example.com/' + "a" * 60 + '\n"""',
            '"""Summary.\n\n`' + "word " * 16 + 'x`\n"""',
            '"""Summary.\n\nIt mirrors `too-many-positional-\narguments` here.\n"""',
            '"""Summary.\n\n' + "a" * 80 + '\n"""',
            '"""Summary.\n\n```\naaa\nbbb\n```\n"""',
            '"""Summary.\n\n>>> compute(\n...     1)\n"""',
            '"""Summary.\n\n| a | b |\n| - | - |\n| 1 | 2 |\n"""',
            '"""Summary.\n\n+---+\n| x |\n+---+\n"""',
            "# aaa\n#\n# bbb\nx = 1",
            "# aaa\nx = 1\n# bbb\ny = 2",
            "# aaa  # noqa: E501 a very long suppression explanation here\nx = 1",
            "x = 1  # " + "abcde " * 13 + "end",
        ],
        ids=[
            "greedy_boundary",
            "single_line_docstring",
            "overlong_summary_line",
            "adjacent_args_entries",
            "bullet_items",
            "label_lines",
            "url_line",
            "backtick_span_only_break",
            "span_hardwrapped_across_lines",
            "unbreakable_token",
            "fenced_code",
            "doctest_lines",
            "markdown_table",
            "ascii_diagram",
            "blank_separated_comments",
            "code_separated_comment_blocks",
            "directive_comment",
            "trailing_comment",
        ],
    )
    def test_ExemptOrFilledStructure_NoViolation(self, source: str) -> None:
        assert list(check_doc_fill(Path("src/x.py"), source)) == []

    def test_NonPythonFile_NotChecked(self) -> None:
        assert list(check_doc_fill(Path("README.md"), "# aaa\n# bbb")) == []


class TestCheckBannedAbbreviation:
    @pytest.mark.parametrize(
        ("source", "word"),
        [
            ("cfg = build()", "cfg"),
            ("def handle(ctx): ...", "ctx"),
            ("async def cfg(): ...", "cfg"),
            ("resp_body = read()", "resp"),
            ("for idx in items: ...", "idx"),
            ("with connect() as conn: ...", "conn"),
            ("user_mgr = build()", "mgr"),
            ("class CfgBuilder: ...", "cfg"),
            ("import configparser as cfg", "cfg"),
        ],
        ids=[
            "assignment_target",
            "parameter",
            "async_function_name",
            "snake_case_prefix",
            "loop_target",
            "with_target",
            "snake_case_suffix",
            "capwords_word",
            "import_alias",
        ],
    )
    def test_BannedAbbreviation_FlagsViolation(self, source: str, word: str) -> None:
        violations = list(check_banned_abbreviation(Path("src/x.py"), source))
        assert len(violations) == 1
        assert violations[0].rule == RS_BANNED_ABBREVIATION
        assert word in violations[0].message

    @pytest.mark.parametrize(
        "source",
        [
            "config = build()",
            "def handle(context): ...",
            "def fetch(request): ...",
            "response_body = read()",
            "for index in items: ...",
            "for i in items: ...",
            "def _iso(dt): ...",
            "db = connect()",
            "result = compute()",
            "class FHIRClient: ...",
            'label = "cfg-value"',
            "response.idx = 1",
            "import configparser as config",
            "from module import resp",
        ],
        ids=[
            "full_word_config",
            "full_word_context",
            "full_word_request",
            "full_word_response",
            "full_word_index",
            "short_loop_counter",
            "sanctioned_datetime_param",
            "sanctioned_db",
            "result_not_res",
            "acronym_class",
            "abbreviation_in_string_literal",
            "abbreviation_in_attribute",
            "import_alias_full_word",
            "import_without_alias",
        ],
    )
    def test_FullWordOrSanctioned_NoViolation(self, source: str) -> None:
        assert list(check_banned_abbreviation(Path("src/x.py"), source)) == []

    def test_NonPythonFile_NotChecked(self) -> None:
        assert list(check_banned_abbreviation(Path("README.md"), "cfg = 1")) == []


class TestCheckDiscouragedClassSuffix:
    @pytest.mark.parametrize(
        ("source", "suffix"),
        [
            ("class ConnectionManager: ...", "Manager"),
            ("class RetryHelper: ...", "Helper"),
            ("class DateUtil: ...", "Util"),
            ("class StringUtils: ...", "Utils"),
            ("class TesterHelper: ...", "Helper"),
        ],
    )
    def test_VagueSuffix_FlagsViolation(self, source: str, suffix: str) -> None:
        violations = list(check_discouraged_class_suffix(Path("src/x.py"), source))
        assert len(violations) == 1
        assert violations[0].rule == RS_DISCOURAGED_CLASS_SUFFIX
        assert suffix in violations[0].message

    @pytest.mark.parametrize(
        "source",
        [
            "class ConnectionPool: ...",
            "class EpicFHIRClient: ...",
            "class TestContextManager: ...",
        ],
        ids=["concrete_noun", "client", "test_class_exempt"],
    )
    def test_ConcreteOrTestName_NoViolation(self, source: str) -> None:
        assert list(check_discouraged_class_suffix(Path("src/x.py"), source)) == []

    def test_NonPythonFile_NotChecked(self) -> None:
        source = "class FooManager: ..."
        assert list(check_discouraged_class_suffix(Path("README.md"), source)) == []


class TestCheckNoNegatedBoolean:
    @pytest.mark.parametrize(
        ("source", "negation"),
        [
            ("def is_not_stale(self): ...", "not"),
            ("is_not_ready = check()", "not"),
            ("def handle(self, should_not_retry): ...", "not"),
            ("has_no_results = compute()", "no"),
            ("async def can_not_connect(self): ...", "not"),
            ("is_not_valid: bool = False", "not"),
        ],
        ids=[
            "method_name",
            "assignment_target",
            "parameter",
            "no_word",
            "async_method",
            "annotated_target",
        ],
    )
    def test_NegatedBoolean_FlagsViolation(self, source: str, negation: str) -> None:
        violations = list(check_no_negated_boolean(Path("src/x.py"), source))
        assert len(violations) == 1
        assert violations[0].rule == RS_NO_NEGATED_BOOLEAN
        assert negation in violations[0].message

    @pytest.mark.parametrize(
        "source",
        [
            "def is_fresh(self): ...",
            "has_results = compute()",
            "is_notable = True",
            "is_north = bearing()",
            "def count_items(self): ...",
            "result = compute()",
            "cannot_connect = True",
            "is_none = value is None",
        ],
        ids=[
            "positive_predicate",
            "positive_has",
            "not_as_leading_substring",
            "no_as_leading_substring",
            "non_boolean_verb",
            "single_word_name",
            "cannot_is_one_word",
            "none_is_not_negation",
        ],
    )
    def test_PositiveOrNonBoolean_NoViolation(self, source: str) -> None:
        assert list(check_no_negated_boolean(Path("src/x.py"), source)) == []

    def test_NonPythonFile_NotChecked(self) -> None:
        assert list(check_no_negated_boolean(Path("README.md"), "is_not_x = 1")) == []


class TestCheckBooleanPrefixRequired:
    @pytest.mark.parametrize(
        ("source", "name"),
        [
            ("def handle(self, valid: bool): ...", "valid"),
            ("enabled: bool = compute()", "enabled"),
            ("self.ready: bool = False", "ready"),
        ],
        ids=[
            "bool_parameter",
            "annotated_variable",
            "annotated_attribute",
        ],
    )
    def test_UnprefixedBoolean_FlagsViolation(self, source: str, name: str) -> None:
        violations = list(check_boolean_prefix_required(Path("src/x.py"), source))
        assert len(violations) == 1
        assert violations[0].rule == RS_BOOLEAN_PREFIX_REQUIRED
        assert name in violations[0].message

    @pytest.mark.parametrize(
        "source",
        [
            "def handle(self, is_valid: bool): ...",
            "has_results: bool = compute()",
            "self.is_ready: bool = False",
            "def render(should_force: bool): ...",
            "def handle(self, can_retry: bool): ...",
            "count: int = 0",
            "def starts_entry(self) -> bool: ...",
            "enabled = True",
            "ready: bool | None = None",
        ],
        ids=[
            "prefixed_parameter",
            "prefixed_variable",
            "prefixed_attribute",
            "should_prefix",
            "can_prefix",
            "non_bool_annotation",
            "bool_returning_function",
            "unannotated_assignment",
            "optional_bool_not_bare",
        ],
    )
    def test_PrefixedOrUnannotated_NoViolation(self, source: str) -> None:
        assert list(check_boolean_prefix_required(Path("src/x.py"), source)) == []

    def test_NonPythonFile_NotChecked(self) -> None:
        path = Path("README.md")
        assert list(check_boolean_prefix_required(path, "valid: bool = True")) == []


class TestCheckExceptionAlias:
    @pytest.mark.parametrize(
        ("source", "alias"),
        [
            ("try:\n    f()\nexcept Exception as e:\n    g()", "e"),
            ("try:\n    f()\nexcept Exception as ex:\n    g()", "ex"),
            ("try:\n    f()\nexcept Exception as err:\n    g()", "err"),
            ("try:\n    f()\nexcept Exception as x:\n    g()", "x"),
        ],
        ids=["single_letter", "ex", "err", "other_single_letter"],
    )
    def test_NonDescriptiveAlias_FlagsViolation(self, source: str, alias: str) -> None:
        violations = list(check_exception_alias(Path("src/x.py"), source))
        assert len(violations) == 1
        assert violations[0].rule == RS_EXCEPTION_ALIAS
        assert alias in violations[0].message

    @pytest.mark.parametrize(
        "source",
        [
            "try:\n    f()\nexcept Exception as exc:\n    g()",
            "try:\n    f()\nexcept Exception as exc2:\n    g()",
            "try:\n    f()\nexcept Exception as validation_error:\n    g()",
            "try:\n    f()\nexcept Exception as _exc:\n    g()",
            "try:\n    f()\nexcept Exception:\n    g()",
        ],
        ids=[
            "blessed_exc",
            "nested_exc2",
            "descriptive_name",
            "four_char_name",
            "no_alias",
        ],
    )
    def test_BlessedDescriptiveOrAbsent_NoViolation(self, source: str) -> None:
        assert list(check_exception_alias(Path("src/x.py"), source)) == []

    def test_NonPythonFile_NotChecked(self) -> None:
        source = "try:\n    f()\nexcept Exception as e:\n    g()"
        assert list(check_exception_alias(Path("README.md"), source)) == []


class TestCheckNoMakeInProduction:
    @pytest.mark.parametrize(
        ("source", "path"),
        [
            ("def make_bundle(): ...", "src/x.py"),
            ("async def make_patient(): ...", "src/app.py"),
            ("class Builder:\n    def make_thing(self): ...", "src/x.py"),
        ],
        ids=["function", "async_function", "method"],
    )
    def test_MakeInProduction_FlagsViolation(self, source: str, path: str) -> None:
        violations = list(check_no_make_in_production(Path(path), source))
        assert len(violations) == 1
        assert violations[0].rule == RS_NO_MAKE_IN_PRODUCTION

    @pytest.mark.parametrize(
        ("source", "path"),
        [
            ("def make_bundle(): ...", "tests/unit/test_x.py"),
            ("def make_bundle(): ...", "src/factory_test.py"),
            ("def make_bundle(): ...", "conftest.py"),
            ("def build_bundle(): ...", "src/x.py"),
            ("def make(): ...", "src/x.py"),
            ("def makedirs(): ...", "src/x.py"),
        ],
        ids=[
            "test_file",
            "test_suffix_file",
            "conftest",
            "build_verb",
            "bare_make",
            "make_prefix_of_word",
        ],
    )
    def test_FixtureLocationOrOtherVerb_NoViolation(
        self, source: str, path: str
    ) -> None:
        assert list(check_no_make_in_production(Path(path), source)) == []

    def test_NonPythonFile_NotChecked(self) -> None:
        source = "def make_x(): ..."
        assert list(check_no_make_in_production(Path("notes.md"), source)) == []


_TEST_PATH = Path("tests/unit/test_x.py")


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
        ["time.sleep(1)", "asyncio.sleep(0.1)"],
        ids=["time", "asyncio"],
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
