import sys
from pathlib import Path

import pytest

from repostyle.rules import (
    RS_ACRONYM_CASING,
    RS_ACRONYM_CASING_IN_PROSE,
    RS_BANNED_ABBREVIATION,
    RS_BEHAVIOR_VERIFICATION_ONLY,
    RS_BOOLEAN_PREFIX_REQUIRED,
    RS_CONDITIONAL_TEST_LOGIC,
    RS_DISCOURAGED_CLASS_SUFFIX,
    RS_DISFAVORED_GCP_TERM,
    RS_DOC_FILL,
    RS_DOC_SUMMARY_OVERFLOW,
    RS_DURATION_AS_TIMEDELTA,
    RS_EQ_HASH_PAIRING,
    RS_EXCEPTION_ALIAS,
    RS_EXCESSIVE_MOCKING,
    RS_GCP_BARE_IDENTIFIER,
    RS_GLUED_CODE_SPAN,
    RS_LOWERCASE_ENTRY_DESCRIPTION,
    RS_NO_ATTRIBUTES_BLOCK,
    RS_NO_DOUBLE_BACKTICKS,
    RS_NO_MAKE_IN_PRODUCTION,
    RS_NO_MOCK_PATCH,
    RS_NO_NEGATED_BOOLEAN,
    RS_NO_PHI_SAFE_EXC_INFO,
    RS_PORT_NO_IMPLEMENTATION,
    RS_PREDICATE_FUNCTION_NAMING,
    RS_SLEEPY_TEST,
    RS_TEMPORAL_MARKER,
    RS_TERMINAL_PUNCTUATION,
    RS_TEST_NAMING,
    RS_UNBACKTICKED_CODE_REFERENCE,
    RS_UNBACKTICKED_SIBLING_SYMBOL,
    check_acronym_casing,
    check_acronym_casing_in_comments,
    check_acronym_casing_in_docstrings,
    check_banned_abbreviation,
    check_behavior_verification_only,
    check_boolean_prefix_required,
    check_comment_temporal_markers,
    check_comment_terminal_punctuation,
    check_conditional_test_logic,
    check_discouraged_class_suffix,
    check_disfavored_gcp_term_in_comments,
    check_disfavored_gcp_term_in_docstrings,
    check_doc_fill,
    check_doc_summary_overflow,
    check_docstring_temporal_markers,
    check_docstring_terminal_punctuation,
    check_duration_as_timedelta,
    check_eq_hash_pairing,
    check_exception_alias,
    check_excessive_mocking,
    check_gcp_bare_identifier,
    check_glued_code_span_in_comments,
    check_glued_code_span_in_docstrings,
    check_glued_code_span_in_md,
    check_lowercase_entry_description,
    check_no_attributes_block,
    check_no_double_backticks_in_docstrings,
    check_no_double_backticks_in_md,
    check_no_make_in_production,
    check_no_mock_patch,
    check_no_negated_boolean,
    check_no_phi_safe_with_exc_info,
    check_port_no_implementation,
    check_predicate_function_naming,
    check_sleepy_test,
    check_test_naming,
    check_unbackticked_code_reference,
    check_unbackticked_sibling_symbol,
    check_unbackticked_sibling_symbol_in_comments,
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
            ("class NatGateway: ...", "NAT"),
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
            "class NATGateway: ...",
            "class Ipv6Handler: ...",
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

    @pytest.mark.parametrize(
        "extra",
        ['["UID"]', '["uid"]'],
        ids=["uppercase-config", "lowercase-config"],
    )
    def test_ConfiguredExtraAcronym_FlagsViolation(
        self, tmp_path: Path, extra: str
    ) -> None:
        (tmp_path / "pyproject.toml").write_text(
            f"[tool.repostyle]\nacronyms-extra = {extra}\n", encoding="utf-8"
        )
        source = "class UidValidator: ...\n"
        target = tmp_path / "x.py"
        target.write_text(source, encoding="utf-8")
        violations = list(check_acronym_casing(target, source))
        assert len(violations) == 1
        assert "'UID' must stay uppercase in 'UidValidator'" in violations[0].message

    def test_ConfiguredExcludedAcronym_NoViolation(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[tool.repostyle]\nacronyms-exclude = ["URL"]\n', encoding="utf-8"
        )
        source = "class UrlBuilder: ...\n"
        target = tmp_path / "x.py"
        target.write_text(source, encoding="utf-8")
        assert list(check_acronym_casing(target, source)) == []

    def test_NonPythonFile_NotChecked(self) -> None:
        assert list(check_acronym_casing(Path("README.md"), "class FhirClient")) == []

    def test_MixedCaseEntryIPv6_LeavesRS001Unchanged(self) -> None:
        """A mixed-case entry does not corrupt RS001's uppercase membership.

        RS001 tokenizes a CapWords name into letter-only words, which a
        digit-bearing acronym like `IPv6` can never equal, so the mixed-case
        entry is inert here rather than firing spuriously.
        """
        source = "class Ipv6Parser: ...\nclass IPv6Parser: ...\n"
        assert list(check_acronym_casing(Path("src/x.py"), source)) == []


class TestCheckAcronymCasingInDocstrings:
    @pytest.mark.parametrize(
        ("prose", "found", "canonical"),
        [
            ("Parses the ipv6 address.", "ipv6", "IPv6"),
            ("Parses the IPV6 address.", "IPV6", "IPv6"),
            ("The Nat gateway advertises it.", "Nat", "NAT"),
            ("Returns the json payload.", "json", "JSON"),
            ("Signs a jwt for the api.", "jwt", "JWT"),
        ],
        ids=["ipv6", "IPV6", "Nat", "json", "jwt-first-of-two"],
    )
    def test_MiscasedAcronym_FlagsWithCanonical(
        self, prose: str, found: str, canonical: str
    ) -> None:
        source = f'def f():\n    """{prose}"""\n'
        violations = list(check_acronym_casing_in_docstrings(Path("src/x.py"), source))
        assert violations[0].rule == RS_ACRONYM_CASING_IN_PROSE
        assert f"'{canonical}' as '{found}'" in violations[0].message

    @pytest.mark.parametrize(
        "prose",
        [
            "Parses the IPv6 address and the NAT gateway.",
            "We identify the nation in the aid record.",
            "Uses `ipv6` and `json` in code font.",
            "See http://host/api/json now.",
            "A smart approach to the problem.",
            "Imported from fhir-ingestor upstream.",
        ],
        ids=[
            "correctly-cased-no-op",
            "substring-not-flagged",
            "backtick-span-skipped",
            "acronym-in-url-skipped",
            "ambiguous-smart-left-alone",
            "hyphenated-compound-left-alone",
        ],
    )
    def test_ConformingProse_NoViolation(self, prose: str) -> None:
        source = f'def f():\n    """{prose}"""\n'
        assert list(check_acronym_casing_in_docstrings(Path("src/x.py"), source)) == []

    def test_ArgsEntryCaption_LeavesParameterName(self) -> None:
        source = (
            "def f(url):\n"
            '    """Summary line.\n\n'
            "    Args:\n"
            "        url: The endpoint to call.\n"
            '    """\n'
        )
        assert list(check_acronym_casing_in_docstrings(Path("src/x.py"), source)) == []

    def test_ExcludedAcronym_NoViolation(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[tool.repostyle]\nacronyms-exclude = ["JSON"]\n', encoding="utf-8"
        )
        source = 'def f():\n    """Returns the json payload."""\n'
        target = tmp_path / "x.py"
        target.write_text(source, encoding="utf-8")
        assert list(check_acronym_casing_in_docstrings(target, source)) == []


class TestCheckAcronymCasingInComments:
    @pytest.mark.parametrize(
        ("comment", "found", "canonical"),
        [
            ("# handles the ipv6 case here", "ipv6", "IPv6"),
            ("# routes through the Nat gateway", "Nat", "NAT"),
        ],
        ids=["ipv6", "Nat"],
    )
    def test_MiscasedAcronym_FlagsWithCanonical(
        self, comment: str, found: str, canonical: str
    ) -> None:
        source = f"{comment}\nx = 1\n"
        violations = list(check_acronym_casing_in_comments(Path("src/x.py"), source))
        assert violations[0].rule == RS_ACRONYM_CASING_IN_PROSE
        assert f"'{canonical}' as '{found}'" in violations[0].message

    @pytest.mark.parametrize(
        "comment",
        [
            "# handles the IPv6 case and the NAT gateway",
            "# json.loads(payload)",
            "# type: ignore for the api call",
        ],
        ids=["correctly-cased", "commented-out-code", "directive"],
    )
    def test_ConformingComment_NoViolation(self, comment: str) -> None:
        source = f"{comment}\nx = 1\n"
        assert list(check_acronym_casing_in_comments(Path("src/x.py"), source)) == []

    def test_TomlComment_FlagsMiscasedAcronym(self) -> None:
        source = "# the ipv6 setting\nkey = 1\n"
        violations = list(
            check_acronym_casing_in_comments(Path("pyproject.toml"), source)
        )
        assert violations[0].rule == RS_ACRONYM_CASING_IN_PROSE


class TestCheckGCPProductNameInDocstrings:
    @pytest.mark.parametrize(
        ("prose", "found", "preferred"),
        [
            ("Uploads to a GCS bucket.", "GCS", "Cloud Storage"),
            ("Runs the job in GCP.", "GCP", "Google Cloud"),
            (
                "Deploys across Google Cloud Platform.",
                "Google Cloud Platform",
                "Google Cloud",
            ),
            ("Reads from Big Query.", "Big Query", "BigQuery"),
            ("Publishes to PubSub.", "PubSub", "Pub/Sub"),
            ("Boots a GCE instance.", "GCE", "Compute Engine"),
            ("A lowercase gcp reference.", "gcp", "Google Cloud"),
        ],
        ids=[
            "GCS",
            "GCP",
            "google-cloud-platform",
            "big-query",
            "pubsub",
            "GCE",
            "lowercase",
        ],
    )
    def test_DisfavoredTerm_FlagsWithPreferred(
        self, prose: str, found: str, preferred: str
    ) -> None:
        source = f'def f():\n    """{prose}"""\n'
        violations = list(
            check_disfavored_gcp_term_in_docstrings(Path("src/x.py"), source)
        )
        assert violations[0].rule == RS_DISFAVORED_GCP_TERM
        assert f"'{found}'" in violations[0].message
        assert f"'{preferred}'" in violations[0].message

    @pytest.mark.parametrize(
        "prose",
        [
            "Uploads to a Cloud Storage bucket in Google Cloud.",
            "Writes each row to Bigtable.",
            "Raises GCSError when the object is missing.",
            "Reads `gcp.storage` and a bare `GCS` in code font.",
            "See gs://bucket/obj for the layout.",
            "Adds a gce-node label to the pool.",
        ],
        ids=[
            "already-preferred",
            "preferred-bigtable-not-reflagged",
            "substring-not-flagged",
            "backtick-span-skipped",
            "uri-skipped",
            "hyphenated-compound-left-alone",
        ],
    )
    def test_ConformingProse_NoViolation(self, prose: str) -> None:
        source = f'def f():\n    """{prose}"""\n'
        assert (
            list(check_disfavored_gcp_term_in_docstrings(Path("src/x.py"), source))
            == []
        )

    def test_ArgsEntryCaption_LeavesParameterName(self) -> None:
        source = (
            "def f(gcp):\n"
            '    """Summary line.\n\n'
            "    Args:\n"
            "        gcp: The GCP project to deploy into.\n"
            '    """\n'
        )
        violations = list(
            check_disfavored_gcp_term_in_docstrings(Path("src/x.py"), source)
        )
        assert len(violations) == 1  # the description's `GCP`, not the `gcp:` caption
        assert violations[0].line == 5

    def test_OneLineDefSignature_NotScannedAsProse(self) -> None:
        source = 'def f(gcp): """Uses GCS."""\n'
        violations = list(
            check_disfavored_gcp_term_in_docstrings(Path("src/x.py"), source)
        )
        assert len(violations) == 1  # the docstring's `GCS`, not the `gcp` parameter
        assert "GCS" in violations[0].message

    def test_TrailingCommentOnClosingLine_NotScanned(self) -> None:
        source = 'def f():\n    """Uses GCS."""  # deploys to GCP\n'
        violations = list(
            check_disfavored_gcp_term_in_docstrings(Path("src/x.py"), source)
        )
        assert len(violations) == 1  # the docstring's `GCS`, not the comment's `GCP`
        assert "GCS" in violations[0].message


class TestCheckGCPProductNameInComments:
    @pytest.mark.parametrize(
        ("comment", "found", "preferred"),
        [
            ("# uploads to a GCS bucket", "GCS", "Cloud Storage"),
            ("# routes through GCP", "GCP", "Google Cloud"),
        ],
        ids=["GCS", "GCP"],
    )
    def test_DisfavoredTerm_FlagsWithPreferred(
        self, comment: str, found: str, preferred: str
    ) -> None:
        source = f"{comment}\nx = 1\n"
        violations = list(
            check_disfavored_gcp_term_in_comments(Path("src/x.py"), source)
        )
        assert violations[0].rule == RS_DISFAVORED_GCP_TERM
        assert f"'{found}'" in violations[0].message
        assert f"'{preferred}'" in violations[0].message

    @pytest.mark.parametrize(
        "comment",
        [
            "# uploads to Cloud Storage in Google Cloud",
            "# gcp.storage.Bucket(name)",
            "# type: ignore for the GCP client",
        ],
        ids=["already-preferred", "commented-out-code", "directive"],
    )
    def test_ConformingComment_NoViolation(self, comment: str) -> None:
        source = f"{comment}\nx = 1\n"
        assert (
            list(check_disfavored_gcp_term_in_comments(Path("src/x.py"), source)) == []
        )

    def test_TomlComment_FlagsDisfavoredTerm(self) -> None:
        source = "# the GCS staging bucket\nkey = 1\n"
        violations = list(
            check_disfavored_gcp_term_in_comments(Path("pyproject.toml"), source)
        )
        assert violations[0].rule == RS_DISFAVORED_GCP_TERM


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


class TestCheckUnbacktickedCodeReference:
    @pytest.mark.parametrize(
        ("source", "token"),
        [
            ('def f() -> None:\n    """Returns None on a miss."""\n', "None"),
            (
                'def f(skip_lines):\n    """Drops skip_lines from the run."""\n',
                "skip_lines",
            ),
            (
                "from x import HttpClient\n\n\n"
                'def f():\n    """Builds a HttpClient."""\n',
                "HttpClient",
            ),
            (
                'def f(node):\n    """Reads node col_offset."""\n'
                "    return node.col_offset\n",
                "col_offset",
            ),
            (
                'def f(skip_lines):\n    """Does it. skip_lines drives it."""\n',
                "skip_lines",
            ),
            (
                'def f(skip_lines):\n    """Does it.\n\n'
                '    - drops skip_lines.\n    """\n',
                "skip_lines",
            ),
        ],
        ids=[
            "literal",
            "snake-case-param",
            "camel-case-import",
            "attribute",
            "code-shape-at-sentence-start",
            "bullet-item",
        ],
    )
    def test_BareCodeNameInProse_FlagsViolation(self, source: str, token: str) -> None:
        violations = list(check_unbackticked_code_reference(Path("src/x.py"), source))
        assert len(violations) == 1
        assert violations[0].rule == RS_UNBACKTICKED_CODE_REFERENCE
        assert f"`{token}`" in violations[0].message

    def test_BareLiteral_ColumnAtToken(self) -> None:
        source = 'def f() -> None:\n    """Returns None on a miss."""\n'
        violations = list(check_unbackticked_code_reference(Path("src/x.py"), source))
        assert (violations[0].line, violations[0].col) == (2, 16)

    @pytest.mark.parametrize(
        "source",
        [
            'def f() -> None:\n    """Returns `None` on a miss."""\n',
            'def f(path):\n    """Reads the path config."""\n',
            'def f() -> None:\n    """Does the thing. None marks a miss."""\n',
            'def f() -> None:\n    """Does it.\n\n    >>> f() is None\n    """\n',
            'def f(count):\n    """Returns the retry_budget as a count."""\n',
            'def f(skip_lines):\n    """Does it.\n\n'
            "    Args:\n        skip_lines: The lines to skip.\n    "
            '"""\n',
            'def f(config_path):\n    """Does it.\n\n'
            "    Args:\n        config_path (str): the path.\n    "
            '"""\n',
            'WARNING = 1\n\n\ndef f():\n    """Does it. WARNING resets state."""\n',
            'A = 1\n\n\ndef f():\n    """A result is returned."""\n',
            "class Note:\n    pass\n\n\n"
            'def f():\n    """Returns it. Please Note the order."""\n',
            'def f() -> None:\n    """See https://x.com/api/None here."""\n',
            'def f(skip_lines):\n    """Writes gs://bucket/skip_lines out."""\n',
        ],
        ids=[
            "backticked",
            "lowercase-english-word",
            "sentence-initial-literal",
            "doctest",
            "code-shaped-but-unbound",
            "args-caption",
            "typed-args-caption",
            "all-caps-english-at-sentence-start",
            "single-letter-name",
            "titlecase-english-word-mid-sentence",
            "name-inside-http-url",
            "name-inside-gs-uri",
        ],
    )
    def test_ConformingProse_NoViolation(self, source: str) -> None:
        assert list(check_unbackticked_code_reference(Path("src/x.py"), source)) == []

    def test_NonPythonFile_NotChecked(self) -> None:
        assert (
            list(check_unbackticked_code_reference(Path("README.md"), "Returns None."))
            == []
        )


class TestCheckUnbacktickedSiblingSymbol:
    def test_TableAndColumnBesideBacktickedClass_FlagsBoth(self) -> None:
        source = (
            '"""Bumps rows below the new floor.\n\n'
            "`ContinuousDiscoverySettings` now rejects a value, so a remote_aes\n"
            "row with continuous_min_study_age below it fails to construct; the\n"
            "remote_aes rows are bumped to the new floor.\n"
            '"""\n'
            "op.execute(\n"
            '    "UPDATE remote_aes SET continuous_min_study_age = 1"\n'
            ")\n"
        )
        violations = list(check_unbackticked_sibling_symbol(Path("src/x.py"), source))
        # `remote_aes` is named twice in the prose but flagged once, so the two
        # flags are one per distinct name, not one per mention.
        assert [violation.rule for violation in violations] == [
            RS_UNBACKTICKED_SIBLING_SYMBOL,
            RS_UNBACKTICKED_SIBLING_SYMBOL,
        ]
        flagged = " ".join(violation.message for violation in violations)
        assert "`remote_aes`" in flagged
        assert "`continuous_min_study_age`" in flagged

    def test_BoundNameSibling_LeftToRS036(self) -> None:
        source = (
            '"""Backticks `min_study_age`. Reads col_offset and remote_aes."""\n'
            "def f():\n"
            "    col_offset = 1\n"
            '    return f"UPDATE remote_aes SET min_study_age = {col_offset}"\n'
        )
        violations = list(check_unbackticked_sibling_symbol(Path("src/x.py"), source))
        assert len(violations) == 1
        assert "`remote_aes`" in violations[0].message

    @pytest.mark.parametrize(
        "source",
        [
            '"""Updates the remote_aes table."""\nx = "UPDATE remote_aes SET y = 1"\n',
            '"""Uses `remote_aes`. The status column drives it."""\n'
            'x = "UPDATE remote_aes SET status = 1"\n',
            '"""Uses `remote_aes` and `continuous_min_study_age`."""\n'
            'x = "UPDATE remote_aes SET continuous_min_study_age = 1"\n',
            '"""Uses `remote_aes`. Mentions some_other_field too."""\n'
            'x = "UPDATE remote_aes SET y = 1"\n',
            '"""Uses `status` here. Updates remote_aes too."""\n'
            'x = "UPDATE remote_aes SET y = 1"\n',
            '"""Bumps rows below the new floor.\n\n'
            "The remote_aes rows shift.\n\n"
            "Example:\n"
            "    x = `HttpClient`\n"
            '"""\n'
            'x = "UPDATE remote_aes SET y = 1"\n',
            '"""Imports study UIDs via `HttpClient`."""\nx = "load study UIDs"\n',
        ],
        ids=[
            "no-backticked-trigger",
            "plain-english-word-matching-string-token",
            "already-backticked-sibling",
            "distinctive-token-without-in-file-evidence",
            "backticked-word-is-not-a-code-symbol",
            "backtick-only-in-example-block",
            "pluralized-acronym-not-a-code-symbol",
        ],
    )
    def test_ConformingDocstring_NoViolation(self, source: str) -> None:
        assert list(check_unbackticked_sibling_symbol(Path("src/x.py"), source)) == []

    def test_NonPythonFile_NotChecked(self) -> None:
        source = '"""Uses `remote_aes`. Reads remote_aes."""\nx = "remote_aes"\n'
        assert list(check_unbackticked_sibling_symbol(Path("README.md"), source)) == []


class TestCheckUnbacktickedSiblingSymbolInComments:
    def test_TableBesideBacktickedClassInBlock_Flags(self) -> None:
        source = (
            "# `ContinuousDiscoverySettings` now rejects a value, so a\n"
            "# remote_aes row below the floor fails to load.\n"
            'op.execute("UPDATE remote_aes SET a = 1")\n'
        )
        violations = list(
            check_unbackticked_sibling_symbol_in_comments(Path("src/x.py"), source)
        )
        assert [violation.rule for violation in violations] == [
            RS_UNBACKTICKED_SIBLING_SYMBOL
        ]
        assert "`remote_aes`" in violations[0].message

    def test_BoundNameSibling_LeftToRS036(self) -> None:
        source = (
            "# Backticks `min_study_age`. Reads col_offset and remote_aes.\n"
            "def f():\n"
            "    col_offset = 1\n"
            '    return f"UPDATE remote_aes SET min_study_age = {col_offset}"\n'
        )
        violations = list(
            check_unbackticked_sibling_symbol_in_comments(Path("src/x.py"), source)
        )
        assert len(violations) == 1
        assert "`remote_aes`" in violations[0].message

    @pytest.mark.parametrize(
        "source",
        [
            '# Updates the remote_aes table.\nx = "UPDATE remote_aes SET y = 1"\n',
            "# Uses `remote_aes` and `min_study_age`.\n"
            'x = "UPDATE remote_aes SET min_study_age = 1"\n',
        ],
        ids=[
            "no-backticked-trigger",
            "already-backticked-sibling",
        ],
    )
    def test_ConformingComment_NoViolation(self, source: str) -> None:
        assert (
            list(
                check_unbackticked_sibling_symbol_in_comments(Path("src/x.py"), source)
            )
            == []
        )

    def test_TrailingComment_NotChecked(self) -> None:
        source = 'x = 1  # `HttpClient` beside bare_field\ny = "bare_field"\n'
        assert (
            list(
                check_unbackticked_sibling_symbol_in_comments(Path("src/x.py"), source)
            )
            == []
        )

    def test_NonPythonFile_NotChecked(self) -> None:
        source = "# Uses `remote_aes`. Reads remote_aes.\nx = 1\n"
        assert (
            list(check_unbackticked_sibling_symbol_in_comments(Path("x.toml"), source))
            == []
        )


class TestCheckGluedCodeSpanInDocstrings:
    @pytest.mark.parametrize(
        "docstring",
        [
            '"""Returns `patient.identifier`\'s value."""',
            '"""Returns the `Observation`s in the bundle."""',
            '"""Returns the bundle once `parse`d."""',
            # The curly apostrophe is the case under test, kept literal despite
            # RUF001's ambiguous-character warning.
            '"""Returns `x`’s value."""',  # noqa: RUF001
        ],
        ids=["possessive", "plural", "verb-suffix", "curly-apostrophe"],
    )
    def test_SuffixGluedToSpan_FlagsViolation(self, docstring: str) -> None:
        source = f"def f():\n    {docstring}\n"
        violations = list(check_glued_code_span_in_docstrings(Path("src/x.py"), source))
        assert len(violations) == 1
        assert violations[0].rule == RS_GLUED_CODE_SPAN

    @pytest.mark.parametrize(
        "docstring",
        [
            '"""Returns the value of `patient.identifier`."""',
            '"""Builds a `str`-typed value."""',
            '"""Returns `x`, then stops."""',
            '"""Returns `x` (the id)."""',
        ],
        ids=["of-form", "hyphen-compound", "punctuation", "paren"],
    )
    def test_SpanEndsOnWordBoundary_NoViolation(self, docstring: str) -> None:
        source = f"def f():\n    {docstring}\n"
        assert list(check_glued_code_span_in_docstrings(Path("src/x.py"), source)) == []

    def test_GluedSuffix_ColumnAtSuffix(self) -> None:
        source = 'def f():\n    """Uses `x`s here."""\n'
        violations = list(check_glued_code_span_in_docstrings(Path("src/x.py"), source))
        assert (violations[0].line, violations[0].col) == (2, 16)

    def test_TwoSpansWithGapBetween_NoViolation(self) -> None:
        # The gap between two spans must not be read as a span of its own, the
        # regression the finditer pairing exists to prevent.
        source = 'def f():\n    """Uses `a` and `b` here."""\n'
        assert list(check_glued_code_span_in_docstrings(Path("src/x.py"), source)) == []

    def test_TwoGluedSpans_FlagsEach(self) -> None:
        source = 'def f():\n    """Uses `a`s and `b`s here."""\n'
        violations = list(check_glued_code_span_in_docstrings(Path("src/x.py"), source))
        assert len(violations) == 2

    def test_GluedSuffixOnLaterLine_MapsToThatLineAndColumn(self) -> None:
        source = 'def f():\n    """Summary.\n\n    Uses `x`s in the body.\n    """\n'
        violations = list(check_glued_code_span_in_docstrings(Path("src/x.py"), source))
        assert (violations[0].line, violations[0].col) == (4, 13)

    def test_SpanCrossingLineBreak_NoFalsePositive(self) -> None:
        # A span whose backticks sit on different physical lines pairs as one
        # span; its trailing backtick must not pair with a later opening one.
        source = 'def f():\n    """Returns the `long\n    reference` value."""\n'
        assert list(check_glued_code_span_in_docstrings(Path("src/x.py"), source)) == []

    def test_EmptySpanBeforeLetter_NoViolation(self) -> None:
        source = 'def f():\n    """text ``s here."""\n'
        assert list(check_glued_code_span_in_docstrings(Path("src/x.py"), source)) == []

    def test_GluedSuffixInsideFence_NoViolation(self) -> None:
        # A fenced code block holds code, not prose; its backticks must not
        # pair with a prose span's and draw a false finding, as the Markdown
        # check also excludes a fence.
        source = (
            "def f():\n"
            '    """Doc.\n'
            "\n"
            "    ```\n"
            "    xs = `Observation`s\n"
            "    ```\n"
            '    """\n'
        )
        assert list(check_glued_code_span_in_docstrings(Path("src/x.py"), source)) == []

    def test_GluedSuffixInExampleSection_NoViolation(self) -> None:
        # An `Example:` section holds code, not prose, whether or not it is
        # fenced; the segmenter excludes it as it does for the other doc rules.
        source = (
            "def f():\n"
            '    """Parses input.\n'
            "\n"
            "    Example:\n"
            "        result = `parse`d output\n"
            '    """\n'
        )
        assert list(check_glued_code_span_in_docstrings(Path("src/x.py"), source)) == []

    def test_GluedSuffixInBullet_FlagsViolation(self) -> None:
        # A bullet item is prose, so a glued span in one is flagged, unlike a
        # code section; the finding lands on the bullet's own line.
        source = 'def f():\n    """Doc.\n\n    - uses `x`s here.\n    """\n'
        violations = list(check_glued_code_span_in_docstrings(Path("src/x.py"), source))
        assert (violations[0].line, violations[0].col) == (4, 15)

    def test_GluedSuffixInConcatenatedDocstring_FlagsViolation(self) -> None:
        # An implicitly-concatenated docstring collapses the value-to-physical
        # line mapping, so its lines are all scanned; the finding still lands
        # on the physical line the glued span sits on.
        source = 'def f():\n    ("""Summary text."""\n     """Uses `item`s here.""")\n'
        violations = list(check_glued_code_span_in_docstrings(Path("src/x.py"), source))
        assert (violations[0].line, violations[0].col) == (3, 20)

    def test_EscapedNewlineWithFence_NoViolation(self) -> None:
        # An escaped newline only adds value lines, not physical ones, so it is
        # not the collapsed-mapping case; the fence stays blanked, unscanned.
        source = (
            "def f():\n"
            '    """Doc.\\nmore.\n'
            "\n"
            "    ```\n"
            "    y = `item`s\n"
            "    ```\n"
            '    """\n'
        )
        assert list(check_glued_code_span_in_docstrings(Path("src/x.py"), source)) == []


class TestCheckGluedCodeSpanInComments:
    def test_SuffixGluedToSpanInComment_FlagsViolation(self) -> None:
        source = "x = 1  # `retries`'s ceiling\n"
        violations = list(check_glued_code_span_in_comments(Path("src/x.py"), source))
        assert len(violations) == 1
        assert violations[0].rule == RS_GLUED_CODE_SPAN

    def test_SpanEndsOnWordBoundaryInComment_NoViolation(self) -> None:
        source = "x = 1  # the ceiling of `retries`\n"
        assert list(check_glued_code_span_in_comments(Path("src/x.py"), source)) == []

    def test_GluedSuffixInComment_ColumnAtSuffix(self) -> None:
        source = "x = 1  # `retries`'s ceiling\n"
        violations = list(check_glued_code_span_in_comments(Path("src/x.py"), source))
        assert (violations[0].line, violations[0].col) == (1, 19)

    def test_YamlComment_FlagsViolation(self) -> None:
        source = "key: 1  # `retries`'s cap\n"
        violations = list(check_glued_code_span_in_comments(Path("cfg.yaml"), source))
        assert len(violations) == 1
        assert violations[0].rule == RS_GLUED_CODE_SPAN

    def test_MarkdownFile_NotCheckedAsComment(self) -> None:
        # `.md` is not a comment-bearing suffix; a heading is the md check's,
        # not the comment check's, so it is not tokenized or double-reported.
        source = "# `Observation`s heading\n"
        assert list(check_glued_code_span_in_comments(Path("README.md"), source)) == []

    def test_MalformedPythonIndentation_DoesNotRaise(self) -> None:
        # An untokenizable file yields nothing rather than aborting the run;
        # the finding on the malformed line is dropped, not reported.
        source = "def f():\n    x = 1\n  y = 2  # `x`'s note\n"
        assert list(check_glued_code_span_in_comments(Path("bad.py"), source)) == []


class TestCheckGluedCodeSpanInMd:
    def test_SuffixGluedToSpanInMd_FlagsViolation(self) -> None:
        violations = list(
            check_glued_code_span_in_md(Path("README.md"), "The `Observation`s ship.")
        )
        assert len(violations) == 1
        assert violations[0].rule == RS_GLUED_CODE_SPAN

    def test_GluedSuffixInsideFence_NoViolation(self) -> None:
        source = "```python\nxs = `Observation`s\n```"
        assert list(check_glued_code_span_in_md(Path("README.md"), source)) == []

    def test_SpanAtEndOfLine_NoViolation(self) -> None:
        assert (
            list(check_glued_code_span_in_md(Path("README.md"), "See `Observation`"))
            == []
        )

    def test_NonMarkdownFile_NotChecked(self) -> None:
        assert (
            list(check_glued_code_span_in_md(Path("notes.txt"), "The `Observation`s."))
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
    def test_MisfilledParagraph_FlagsViolation(
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
        "path",
        [Path("config.toml"), Path("config.yaml"), Path("config.yml")],
        ids=["toml", "yaml", "yml"],
    )
    def test_UnderwrappedCommentBlock_FlagsAcrossCommentLanguages(
        self, path: Path
    ) -> None:
        source = "# aaa\n# bbb\nkey = 1\n"
        violations = list(check_doc_fill(path, source))
        assert [(v.rule, v.line) for v in violations] == [(RS_DOC_FILL, 1)]

    @pytest.mark.parametrize(
        ("path", "assignment"),
        [(Path("config.toml"), "key = 1\n"), (Path("config.yaml"), "key: 1\n")],
        ids=["toml", "yaml"],
    )
    def test_OverlongComment_FlagsAcrossCommentLanguages(
        self, path: Path, assignment: str
    ) -> None:
        source = "# " + "abcde " * 13 + "end\n" + assignment
        violations = list(check_doc_fill(path, source))
        assert [v.rule for v in violations] == [RS_DOC_FILL]
        assert "exceeds" in violations[0].message

    @pytest.mark.parametrize(
        "source",
        [
            'def f():\n    """Summary.\n\n    ' + "a" * 72 + "\n    bbbb\n" + '    """',
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
            "# aaa\n# codespell:ignore-begin\nx = 1",
            "# aaa\n# nosec\nx = 1",
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
            "codespell_directive_splits_block",
            "nosec_directive_splits_block",
            "trailing_comment",
        ],
    )
    def test_ExemptOrFilledStructure_NoViolation(self, source: str) -> None:
        assert list(check_doc_fill(Path("src/x.py"), source)) == []

    def test_HashInsideTomlString_NotTreatedAsComment(self) -> None:
        source = 'key = "' + "a" * 90 + '#x"\n'
        assert list(check_doc_fill(Path("config.toml"), source)) == []

    def test_NonPythonFile_NotChecked(self) -> None:
        assert list(check_doc_fill(Path("README.md"), "# aaa\n# bbb")) == []

    def test_UnparseablePython_NotChecked(self) -> None:
        # An over-long comment in a .py file that does not parse: the check
        # stays silent because --fix cannot rewrap it.
        source = "def f(:\n# " + "abcde " * 13 + "end\n"
        assert list(check_doc_fill(Path("src/x.py"), source)) == []


class TestCheckDocSummaryOverflow:
    @pytest.mark.parametrize(
        ("source", "line"),
        [
            ('"""' + "abcde " * 13 + 'end."""', 1),
            (
                '"""' + "abcde " * 13 + 'end summary.\n\nBody.\n"""',
                1,
            ),
            (
                'def f():\n    """' + "abcde " * 12 + 'end."""',
                2,
            ),
            ('"""' + "a" * 74 + '"""', 1),
        ],
        ids=[
            "single_line_docstring",
            "multiline_docstring_summary",
            "indented_opening_line",
            "boundary_80_columns",
        ],
    )
    def test_OverlongSummaryLine_FlagsViolation(self, source: str, line: int) -> None:
        violations = list(check_doc_summary_overflow(Path("src/x.py"), source))
        assert [(v.rule, v.line) for v in violations] == [
            (RS_DOC_SUMMARY_OVERFLOW, line)
        ]

    def test_IndentedSummaryLine_ColumnAtDocstringIndent(self) -> None:
        source = 'def f():\n    """' + "abcde " * 12 + 'end."""'
        violations = list(check_doc_summary_overflow(Path("src/x.py"), source))
        assert (violations[0].line, violations[0].col) == (2, 5)

    def test_SummaryLineAtExactly79Columns_NoViolation(self) -> None:
        source = '"""' + "a" * 73 + '"""'
        assert len(source) == 79
        assert list(check_doc_summary_overflow(Path("src/x.py"), source)) == []

    def test_OverlongBodyParagraphOnly_NoViolation(self) -> None:
        # A short summary with an overlong body paragraph is RS009's rule to
        # enforce, not RS035's — the summary line itself fits.
        source = '"""Summary.\n\n' + "abcde " * 13 + 'end\n"""'
        assert list(check_doc_summary_overflow(Path("src/x.py"), source)) == []

    def test_NonPythonFile_NotChecked(self) -> None:
        source = "# " + "a" * 90
        assert list(check_doc_summary_overflow(Path("config.toml"), source)) == []

    def test_UnparseablePython_NotChecked(self) -> None:
        source = "def f(:\n" + '"""' + "a" * 90 + '"""\n'
        assert list(check_doc_summary_overflow(Path("src/x.py"), source)) == []


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


class TestCheckGCPBareIdentifier:
    @pytest.mark.parametrize(
        ("source", "name"),
        [
            ("def f(project: str): ...", "project"),
            ("def f(bucket: str): ...", "bucket"),
            ("def f(dataset: str): ...", "dataset"),
            ("def f(topic: str | None): ...", "topic"),
            ("def f(subscription: Optional[str]): ...", "subscription"),
            ('def f(instance: "str"): ...', "instance"),
            ("class C:\n    def m(self, project: str): ...", "project"),
            ("def f(*, dataset: str): ...", "dataset"),
        ],
        ids=[
            "project",
            "bucket",
            "dataset",
            "union-optional",
            "optional-subscript",
            "forward-ref",
            "method-parameter",
            "keyword-only",
        ],
    )
    def test_BareCollectionNounStrParam_FlagsWithIdSuffix(
        self, source: str, name: str
    ) -> None:
        violations = list(check_gcp_bare_identifier(Path("src/x.py"), source))
        assert violations[0].rule == RS_GCP_BARE_IDENTIFIER
        assert f"'{name}'" in violations[0].message
        assert f"'{name}_id'" in violations[0].message

    @pytest.mark.parametrize(
        "source",
        [
            "def f(project_id: str): ...",
            "def f(bucket_name: str): ...",
            "def f(project): ...",
            "def f(project: Bucket): ...",
            "def f(topic: list[str]): ...",
            "def f(project: str | int): ...",
            "def f(name: str, region: str): ...",
            "def f(*args: str, **kwargs: str): ...",
        ],
        ids=[
            "already-id-suffixed",
            "other-suffix",
            "unannotated",
            "non-string-type",
            "list-of-str",
            "mixed-union-non-str-arm",
            "noun-not-in-set",
            "varargs-kwargs",
        ],
    )
    def test_NonBareIdentifier_NoViolation(self, source: str) -> None:
        assert list(check_gcp_bare_identifier(Path("src/x.py"), source)) == []

    def test_TwoBareParams_FlagsEach(self) -> None:
        source = "def grant(project: str, bucket: str) -> None: ..."
        violations = list(check_gcp_bare_identifier(Path("src/x.py"), source))
        assert [v.message.split("'")[1] for v in violations] == ["project", "bucket"]

    def test_NonPythonFile_NotChecked(self) -> None:
        source = "def f(project: str): ..."
        assert list(check_gcp_bare_identifier(Path("notes.md"), source)) == []


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


_DOC_PATH = Path("src/x.py")

_DOC_SINGLE_LINE_ENTRY = (
    'def f(foo):\n    """Do the thing.\n\n    Args:\n'
    '        foo: the widget to process.\n    """\n'
)
_DOC_MULTI_LINE_ENTRY = (
    'def f(bar):\n    """Do the thing.\n\n    Args:\n'
    "        bar: the widget that wraps across\n"
    '            two lines of description.\n    """\n'
)
_DOC_COLON_INTRO = (
    'def f():\n    """Do the thing.\n\n    The steps are as follows:\n    """\n'
)
_DOC_EXAMPLE_SECTION = (
    'def f():\n    """Do the thing.\n\n    Example:\n'
    '        >>> f()\n        result\n    """\n'
)
# A Returns description that wraps at the entry margin (no hanging indent) is
# one multi-line entry, not two single-line labels.
_DOC_SAME_INDENT_RETURNS = (
    'def f():\n    """Do the thing.\n\n    Returns:\n'
    "        A tuple of the parsed bundle and the\n"
    '        count of records.\n    """\n'
)


class TestCheckDocstringTerminalPunctuation:
    @pytest.mark.parametrize(
        "source",
        [
            'def f():\n    """Resolve the lease."""\n',
            'def f():\n    """Ready to go?"""\n',
            'def f():\n    """Do it.\n\n    The body states the contract.\n    """\n',
            _DOC_SINGLE_LINE_ENTRY,
            _DOC_MULTI_LINE_ENTRY,
            _DOC_COLON_INTRO,
            _DOC_EXAMPLE_SECTION,
            _DOC_SAME_INDENT_RETURNS,
            'def f():\n    """Do it.\n\n    See the spec at\n'
            '    https://example.com/spec\n    """\n',
            'def f():\n    """Do it.\n\n    - first point\n    - second\n    """\n',
            'def f():\n    """Do it.\n\n    ```\n    code here\n    ```\n    """\n',
        ],
        ids=[
            "summary-with-period",
            "summary-question-mark",
            "body-with-period",
            "single-line-entry-with-period",
            "multi-line-entry-with-period",
            "colon-list-intro",
            "example-section-code",
            "same-indent-returns-with-period",
            "body-url-tail",
            "bullet-list",
            "fenced-code",
        ],
    )
    def test_ConformingDocstring_NoViolation(self, source: str) -> None:
        assert list(check_docstring_terminal_punctuation(_DOC_PATH, source)) == []

    def test_SingleLineSummaryWithoutTerminal_FlagsAtSummary(self) -> None:
        source = 'def f():\n    """Resolve the lease"""\n'
        violations = list(check_docstring_terminal_punctuation(_DOC_PATH, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_TERMINAL_PUNCTUATION
        assert (violations[0].line, violations[0].col) == (2, 5)
        assert "terminal punctuation" in violations[0].message

    def test_ModuleDocstringWithoutTerminal_FlagsAtColumnOne(self) -> None:
        violations = list(
            check_docstring_terminal_punctuation(_DOC_PATH, '"""Resolve the lease"""\n')
        )
        assert [(v.rule, v.line, v.col) for v in violations] == [
            (RS_TERMINAL_PUNCTUATION, 1, 1)
        ]

    def test_BodyParagraphWithoutTerminal_FlagsAtBody(self) -> None:
        source = (
            'def f():\n    """Do it.\n\n    The body has no terminal mark\n    """\n'
        )
        violations = list(check_docstring_terminal_punctuation(_DOC_PATH, source))
        assert [(v.rule, v.line) for v in violations] == [(RS_TERMINAL_PUNCTUATION, 4)]

    def test_MultiLineSummaryWithoutTerminal_FlagsAtLastLine(self) -> None:
        source = (
            'def f():\n    """Resolve the lease for the tenant named in the\n'
            '    request payload\n    """\n'
        )
        violations = list(check_docstring_terminal_punctuation(_DOC_PATH, source))
        assert [(v.rule, v.line) for v in violations] == [(RS_TERMINAL_PUNCTUATION, 3)]

    def test_SingleLineEntryWithoutTerminal_FlagsAtEntry(self) -> None:
        source = (
            'def f(foo):\n    """Do the thing.\n\n    Args:\n'
            '        foo: the widget\n    """\n'
        )
        violations = list(check_docstring_terminal_punctuation(_DOC_PATH, source))
        assert [(v.rule, v.line) for v in violations] == [(RS_TERMINAL_PUNCTUATION, 5)]

    def test_RaisesEntryWithoutTerminal_FlagsAtEntry(self) -> None:
        source = (
            'def f():\n    """Do the thing.\n\n    Raises:\n'
            '        ValueError: when the input is bad\n    """\n'
        )
        violations = list(check_docstring_terminal_punctuation(_DOC_PATH, source))
        assert [(v.rule, v.line) for v in violations] == [(RS_TERMINAL_PUNCTUATION, 5)]

    def test_MultiLineEntryWithoutTerminal_FlagsAtLastLine(self) -> None:
        source = (
            'def f():\n    """Do the thing.\n\n    Returns:\n'
            "        A tuple of the parsed bundle and the\n"
            '        count of records\n    """\n'
        )
        violations = list(check_docstring_terminal_punctuation(_DOC_PATH, source))
        assert [(v.rule, v.line) for v in violations] == [(RS_TERMINAL_PUNCTUATION, 6)]

    def test_MultiEntrySection_FlagsOnlyOffendingEntry(self) -> None:
        source = (
            'def f(foo, bar):\n    """Do the thing.\n\n    Args:\n'
            "        foo: the first widget.\n"
            '        bar: the second widget\n    """\n'
        )
        violations = list(check_docstring_terminal_punctuation(_DOC_PATH, source))
        assert [(v.rule, v.line) for v in violations] == [(RS_TERMINAL_PUNCTUATION, 6)]


class TestCheckLowercaseEntryDescription:
    @pytest.mark.parametrize(
        "source",
        [
            'def f(foo):\n    """Do the thing.\n\n    Args:\n'
            '        foo: A widget.\n    """\n',
            'def f():\n    """Do the thing.\n\n    Returns:\n'
            '        The parsed bundle.\n    """\n',
            'def f():\n    """Do the thing.\n\n    Raises:\n'
            '        ValueError: If the input is bad.\n    """\n',
            'def f(foo):\n    """Do the thing.\n\n    Args:\n'
            '        foo: `None` when unset.\n    """\n',
            'def f(foo):\n    """Do the thing.\n\n    Args:\n'
            '        foo: json.dumps of the payload.\n    """\n',
            'def f(foo):\n    """Do the thing.\n\n    Args:\n'
            '        foo: col_offset of the node.\n    """\n',
            'def f(foo):\n    """Do the thing.\n\n    Args:\n'
            '        foo: 3 retries at most.\n    """\n',
            'def f(foo):\n    """Do the thing.\n\n    Args:\n        foo:\n    """\n',
        ],
        ids=[
            "args-capitalized",
            "returns-nameless-capitalized",
            "raises-capitalized",
            "opens-backtick-span",
            "opens-dotted-path",
            "opens-distinctive-token",
            "opens-digit",
            "empty-description",
        ],
    )
    def test_ConformingEntry_NoViolation(self, source: str) -> None:
        assert list(check_lowercase_entry_description(_DOC_PATH, source)) == []

    def test_LowercaseArgsDescription_FlagsAtEntry(self) -> None:
        source = (
            'def f(bar):\n    """Do the thing.\n\n    Args:\n'
            '        bar: a bar.\n    """\n'
        )
        violations = list(check_lowercase_entry_description(_DOC_PATH, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_LOWERCASE_ENTRY_DESCRIPTION
        assert (violations[0].line, violations[0].col) == (5, 9)
        assert "lowercase" in violations[0].message

    def test_LowercaseRaisesDescription_FlagsAtEntry(self) -> None:
        source = (
            'def f():\n    """Do the thing.\n\n    Raises:\n'
            '        NotFoundError: if a foo is not found.\n    """\n'
        )
        violations = list(check_lowercase_entry_description(_DOC_PATH, source))
        assert [(v.rule, v.line) for v in violations] == [
            (RS_LOWERCASE_ENTRY_DESCRIPTION, 5)
        ]

    def test_NamelessReturnsLowercase_FlagsAtEntry(self) -> None:
        source = (
            'def f():\n    """Do the thing.\n\n    Returns:\n'
            '        the parsed bundle.\n    """\n'
        )
        violations = list(check_lowercase_entry_description(_DOC_PATH, source))
        assert [(v.rule, v.line) for v in violations] == [
            (RS_LOWERCASE_ENTRY_DESCRIPTION, 5)
        ]

    def test_MultiLineEntryLowercase_FlagsAtFirstLine(self) -> None:
        source = (
            'def f():\n    """Do the thing.\n\n    Returns:\n'
            "        the parsed bundle and the\n"
            '        record count.\n    """\n'
        )
        violations = list(check_lowercase_entry_description(_DOC_PATH, source))
        assert [(v.rule, v.line) for v in violations] == [
            (RS_LOWERCASE_ENTRY_DESCRIPTION, 5)
        ]

    def test_MultiEntrySection_FlagsOnlyOffendingEntry(self) -> None:
        source = (
            'def f(foo, bar):\n    """Do the thing.\n\n    Args:\n'
            "        foo: A first widget.\n"
            '        bar: a second widget.\n    """\n'
        )
        violations = list(check_lowercase_entry_description(_DOC_PATH, source))
        assert [(v.rule, v.line) for v in violations] == [
            (RS_LOWERCASE_ENTRY_DESCRIPTION, 6)
        ]


class TestCheckCommentTerminalPunctuation:
    @pytest.mark.parametrize(
        "source",
        [
            "# Does a foo\nx = 1\n",
            "x = 1  # Does a foo\n",
            "# This comment wraps across two lines and ends\n# with a period.\nx = 1\n",
            "x = 1  # noqa: E501\n",
            "# def helper():\n#     return 1\nx = 1\n",
            "# The spec lives at\n# https://example.com/spec\nx = 1\n",
            "# -*- coding: utf-8 -*-\nx = 1\n",
            "# handles the retry path.\nx = 1\n",
            "# First standalone note\n\n# Second standalone note\nx = 1\n",
            "# Rescue still fires without the apostrophe\n"
            "# codespell:ignore-begin\nx = 1\n",
            "# Spawns the subprocess with a fixed argv\n# nosec\nx = 1\n",
        ],
        ids=[
            "standalone-fragment",
            "trailing-fragment",
            "multiline-prose-with-period",
            "trailing-directive",
            "commented-out-code",
            "url-tail",
            "coding-declaration",
            "lowercase-not-prose",
            "blank-gap-separate-blocks",
            "codespell-directive-splits-block",
            "nosec-directive-splits-block",
        ],
    )
    def test_ConformingComment_NoViolation(self, source: str) -> None:
        assert list(check_comment_terminal_punctuation(_DOC_PATH, source)) == []

    def test_StandaloneFragmentWithPeriod_FlagsFragment(self) -> None:
        violations = list(
            check_comment_terminal_punctuation(_DOC_PATH, "# Does a foo.\nx = 1\n")
        )
        assert [(v.rule, v.line) for v in violations] == [(RS_TERMINAL_PUNCTUATION, 1)]
        assert "fragment" in violations[0].message

    def test_TrailingProseWithPeriod_FlagsFragmentAtColumn(self) -> None:
        source = "x = 1  # Returns the widget.\n"
        violations = list(check_comment_terminal_punctuation(_DOC_PATH, source))
        assert (violations[0].line, violations[0].col) == (1, 8)

    def test_MultilineProseWithoutTerminal_FlagsProseAtLastLine(self) -> None:
        source = (
            "# This comment wraps across two lines and ends\n"
            "# without any terminal mark\nx = 1\n"
        )
        violations = list(check_comment_terminal_punctuation(_DOC_PATH, source))
        assert [(v.rule, v.line) for v in violations] == [(RS_TERMINAL_PUNCTUATION, 2)]
        assert "prose" in violations[0].message

    def test_MultiSentenceSingleLineWithoutTerminal_FlagsProse(self) -> None:
        source = "# I like pie. I like cake\nx = 1\n"
        violations = list(check_comment_terminal_punctuation(_DOC_PATH, source))
        assert [(v.rule, v.line) for v in violations] == [(RS_TERMINAL_PUNCTUATION, 1)]

    @pytest.mark.parametrize(
        "path",
        [Path("config.toml"), Path("config.yaml")],
        ids=["toml", "yaml"],
    )
    def test_MultilineProseWithoutTerminal_FlagsAcrossCommentLanguages(
        self, path: Path
    ) -> None:
        source = (
            "# This comment spans two lines and ends\n"
            "# without any terminal mark\nkey: 1\n"
        )
        violations = list(check_comment_terminal_punctuation(path, source))
        assert [(v.rule, v.line) for v in violations] == [(RS_TERMINAL_PUNCTUATION, 2)]

    def test_YamlTrailingMultiSentence_FlagsProse(self) -> None:
        source = "key: 1  # First sentence. Second sentence with no terminal mark\n"
        violations = list(
            check_comment_terminal_punctuation(Path("config.yaml"), source)
        )
        assert [(v.rule, v.line) for v in violations] == [(RS_TERMINAL_PUNCTUATION, 1)]

    def test_NonPythonFile_NoViolation(self) -> None:
        source = "# A prose comment with a trailing period.\n"
        assert list(check_comment_terminal_punctuation(Path("notes.txt"), source)) == []

    def test_DirectiveSplitsBlockFromProse_NoViolation(self) -> None:
        source = "# A standalone prose comment line\n# type: ignore\nx = 1\n"
        assert list(check_comment_terminal_punctuation(_DOC_PATH, source)) == []

    def test_HashInsideYamlQuotedScalar_NotTreatedAsComment(self) -> None:
        source = 'key: "a value. with a period inside"\n'
        assert (
            list(check_comment_terminal_punctuation(Path("config.yaml"), source)) == []
        )
