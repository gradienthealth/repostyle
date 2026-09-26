import sys
from pathlib import Path

import pytest

from repostyle.rules import (
    RS_BANNED_ABBREVIATION,
    RS_BOOLEAN_PREFIX_REQUIRED,
    RS_DISCOURAGED_CLASS_SUFFIX,
    RS_EQ_HASH_PAIRING,
    RS_EXCEPTION_ALIAS,
    RS_NO_MAKE_IN_PRODUCTION,
    RS_NO_NEGATED_BOOLEAN,
    RS_PREDICATE_FUNCTION_NAMING,
    RS_TEMPORAL_MARKER,
    check_banned_abbreviation,
    check_boolean_prefix_required,
    check_comment_temporal_markers,
    check_discouraged_class_suffix,
    check_docstring_temporal_markers,
    check_eq_hash_pairing,
    check_exception_alias,
    check_no_make_in_production,
    check_no_negated_boolean,
    check_predicate_function_naming,
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


class TestCheckEqHashPairing:
    @pytest.mark.parametrize(
        ("source", "half"),
        [
            ("class Money:\n    def __eq__(self, other): return True\n", "__hash__"),
            (
                "class Money(Base):\n    def __eq__(self, other): return True\n",
                "__hash__",
            ),
            ("class Token:\n    def __hash__(self): return 1\n", "__eq__"),
        ],
        ids=["eq-without-hash", "eq-without-hash-with-base", "hash-without-eq"],
    )
    def test_LoneHalf_FlagsViolation(self, source: str, half: str) -> None:
        violations = list(check_eq_hash_pairing(Path("src/x.py"), source))
        assert len(violations) == 1
        assert violations[0].rule == RS_EQ_HASH_PAIRING
        assert half in violations[0].message

    @pytest.mark.parametrize(
        "source",
        [
            "class Money:\n"
            "    def __eq__(self, other): return True\n"
            "    def __hash__(self): return 1\n",
            "class Plain:\n    x = 1\n",
            "@dataclass\nclass Money:\n    def __eq__(self, other): return True\n",
            "@attrs.define\nclass Money:\n    def __eq__(self, other): return True\n",
            "class Money:\n"
            "    def __eq__(self, other): return True\n"
            "    __hash__ = None\n",
            "class Token(Base):\n    def __hash__(self): return 1\n",
        ],
        ids=[
            "both-defined",
            "neither-defined",
            "dataclass-exempt",
            "attrs-exempt",
            "explicit-hash-none",
            "hash-without-eq-inherits-base",
        ],
    )
    def test_PairedExemptOrNeither_NoViolation(self, source: str) -> None:
        assert list(check_eq_hash_pairing(Path("src/x.py"), source)) == []

    def test_NonPythonFile_NotChecked(self) -> None:
        source = "class Money:\n    def __eq__(self, other): return True\n"
        assert list(check_eq_hash_pairing(Path("README.md"), source)) == []


class TestCheckPredicateFunctionNaming:
    @pytest.mark.parametrize(
        "name",
        ["valid", "ready", "enabled", "_valid"],
        ids=["adjective", "state", "past-participle", "private-adjective"],
    )
    def test_BareStateWord_FlagsViolation(self, name: str) -> None:
        source = f"def {name}(self) -> bool: ...\n"
        violations = list(check_predicate_function_naming(Path("src/x.py"), source))
        assert len(violations) == 1
        assert violations[0].rule == RS_PREDICATE_FUNCTION_NAMING
        assert f"is_{name.lstrip('_')}" in violations[0].message

    @pytest.mark.parametrize(
        "source",
        [
            "def is_valid(self) -> bool: ...\n",
            "def needs(self) -> bool: ...\n",
            "def matches(self) -> bool: ...\n",
            "def field_has_docstring() -> bool: ...\n",
            "def valid(self): ...\n",
            "def valid(self) -> int: ...\n",
            "def __eq__(self, other) -> bool: ...\n",
            "class C:\n    @x.setter\n    def valid(self, v) -> bool: ...\n",
            "class C:\n    @override\n    def valid(self) -> bool: ...\n",
        ],
        ids=[
            "prefixed",
            "needs-prefix",
            "third-person-verb",
            "multi-word",
            "no-annotation",
            "non-bool-return",
            "dunder",
            "property-setter",
            "override",
        ],
    )
    def test_QuestionFormOrExempt_NoViolation(self, source: str) -> None:
        assert list(check_predicate_function_naming(Path("src/x.py"), source)) == []

    def test_NonPythonFile_NotChecked(self) -> None:
        assert (
            list(
                check_predicate_function_naming(
                    Path("README.md"), "def valid() -> bool: ..."
                )
            )
            == []
        )


class TestCheckDocstringTemporalMarkers:
    @pytest.mark.parametrize(
        "marker",
        [
            "previously",
            "used to",
            "formerly",
            "originally",
            "as discussed",
            "we decided",
            "for now",
            "changed to",
            "switched to",
        ],
    )
    def test_MarkerInDocstringProse_FlagsViolation(self, marker: str) -> None:
        source = f'def f(x):\n    """Returns x. This {marker} held here."""\n'
        violations = list(check_docstring_temporal_markers(Path("src/x.py"), source))
        assert len(violations) == 1
        assert violations[0].rule == RS_TEMPORAL_MARKER
        assert f"'{marker}'" in violations[0].message

    def test_TwoDistinctMarkers_FlagsEach(self) -> None:
        source = (
            "def f(x):\n"
            '    """Returns x.\n'
            "\n"
            "    It formerly returned a dict, as discussed in the review.\n"
            '    """\n'
        )
        violations = list(check_docstring_temporal_markers(Path("src/x.py"), source))
        assert len(violations) == 2
        assert {v.rule for v in violations} == {RS_TEMPORAL_MARKER}

    @pytest.mark.parametrize(
        "source",
        [
            'def f(x):\n    """Returns x from the current inputs."""\n',
            'def f(x):\n    """Flags an opening like `used to` in a summary."""\n',
        ],
        ids=["clean", "marker-in-backticks"],
    )
    def test_NoBareMarker_NoViolation(self, source: str) -> None:
        assert list(check_docstring_temporal_markers(Path("src/x.py"), source)) == []

    def test_NonPythonFile_NotChecked(self) -> None:
        source = 'def f():\n    """Previously returned a dict."""\n'
        assert list(check_docstring_temporal_markers(Path("README.md"), source)) == []


class TestCheckCommentTemporalMarkers:
    @pytest.mark.parametrize(
        ("source", "marker"),
        [
            ("# we decided to cache this here\nx = 1\n", "we decided"),
            ("x = 1  # switched to a set for lookup speed\n", "switched to"),
        ],
        ids=["own-line", "trailing"],
    )
    def test_MarkerInComment_FlagsViolation(self, source: str, marker: str) -> None:
        violations = list(check_comment_temporal_markers(Path("src/x.py"), source))
        assert len(violations) == 1
        assert violations[0].rule == RS_TEMPORAL_MARKER
        assert f"'{marker}'" in violations[0].message

    @pytest.mark.parametrize(
        "source",
        [
            "# type: ignore we decided this\nx = 1\n",
            "# reset switched_to_set on load\nx = 1\n",
            "# caches the lookup, which dominates the request time\nx = 1\n",
            "# quotes `for now` only as a referenced token\nx = 1\n",
        ],
        ids=["directive", "underscore-boundary", "clean", "backticked-marker"],
    )
    def test_NoBareMarker_NoViolation(self, source: str) -> None:
        assert list(check_comment_temporal_markers(Path("src/x.py"), source)) == []

    def test_NonCommentSuffix_NotChecked(self) -> None:
        source = "# we decided this here\nx = 1\n"
        assert list(check_comment_temporal_markers(Path("x.md"), source)) == []


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
