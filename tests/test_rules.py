import sys
from pathlib import Path

import pytest

from repostyle.rules import (
    RS_ACRONYM_CASING,
    RS_ACRONYM_CASING_IN_PROSE,
    RS_DISFAVORED_GCP_TERM,
    RS_TEST_NAMING,
    check_acronym_casing,
    check_acronym_casing_in_comments,
    check_acronym_casing_in_docstrings,
    check_disfavored_gcp_term_in_comments,
    check_disfavored_gcp_term_in_docstrings,
    check_test_naming,
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
            "Imported from fhir-parser upstream.",
            "Reads the backlog from .repostyle-baseline.json first.",
            "Parses it with json.loads before writing.",
        ],
        ids=[
            "correctly-cased-no-op",
            "substring-not-flagged",
            "backtick-span-skipped",
            "acronym-in-url-skipped",
            "ambiguous-smart-left-alone",
            "hyphenated-compound-left-alone",
            "file-extension-left-alone",
            "dotted-attribute-left-alone",
        ],
    )
    def test_ConformingProse_NoViolation(self, prose: str) -> None:
        source = f'def f():\n    """{prose}"""\n'
        assert list(check_acronym_casing_in_docstrings(Path("src/x.py"), source)) == []

    def test_SentenceFinalAcronym_StillFlags(self) -> None:
        source = 'def f():\n    """Returns the payload as json."""\n'
        violations = list(check_acronym_casing_in_docstrings(Path("src/x.py"), source))
        assert violations[0].rule == RS_ACRONYM_CASING_IN_PROSE

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
            "Calls gcs.upload once the object is staged.",
            "Reads the bucket name from config.gcs at startup.",
        ],
        ids=[
            "already-preferred",
            "preferred-bigtable-not-reflagged",
            "substring-not-flagged",
            "backtick-span-skipped",
            "uri-skipped",
            "hyphenated-compound-left-alone",
            "dotted-attribute-left-alone",
            "dotted-suffix-left-alone",
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

    @pytest.mark.parametrize(
        "globs_value",
        ['["hooks/test_*.py"]', '"hooks/test_*.py"'],
        ids=["list", "bare_string"],
    )
    def test_ConfiguredGlobs_CheckMatchingFile(
        self, tmp_path: Path, globs_value: str
    ) -> None:
        target = _naming_scope_target(tmp_path, globs_value, "hooks/test_x.py")
        violations = list(check_test_naming(target, "def test_bad_name(): ..."))
        assert len(violations) == 1
        assert violations[0].rule == RS_TEST_NAMING

    def test_ConfiguredGlobs_ReplaceDefaultScope(self, tmp_path: Path) -> None:
        target = _naming_scope_target(
            tmp_path, '["hooks/test_*.py"]', "tests/unit/test_x.py"
        )
        assert list(check_test_naming(target, "def test_bad_name(): ...")) == []

    def test_ConfiguredGlobs_ExemptConftest(self, tmp_path: Path) -> None:
        target = _naming_scope_target(tmp_path, '["hooks/*.py"]', "hooks/conftest.py")
        assert list(check_test_naming(target, "def test_bad_name(): ...")) == []


def _naming_scope_target(tmp_path: Path, globs_value: str, relative: str) -> Path:
    """Writes a pyproject configuring `test-naming-globs` and returns a path.

    The returned path sits under `tmp_path` at `relative`; the file itself is
    never written, since `check_test_naming` takes the source separately.
    """
    (tmp_path / "pyproject.toml").write_text(
        f"[tool.repostyle]\ntest-naming-globs = {globs_value}\n", encoding="utf-8"
    )
    return tmp_path / relative
