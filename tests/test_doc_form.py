from pathlib import Path

import pytest

from repostyle.rules import (
    RS_FIELD_COMMENT_AS_DOCSTRING,
    RS_FILLER_DOCSTRING_OPENING,
    RS_IMPERATIVE_DOCSTRING_OPENING,
    RS_SUMMARY_COMMENT_AS_DOCSTRING,
    check_field_comment_as_docstring,
    check_filler_docstring_opening,
    check_imperative_docstring_opening,
    check_summary_comment_as_docstring,
)
from repostyle.rules.imperative_verbs import (
    IMPERATIVE_VERB_CONJUGATIONS,
    NON_TRIVIAL_CONJUGATIONS,
)

_SRC = Path("src/x.py")


class TestCheckSummaryCommentAsDocstring:
    @pytest.mark.parametrize(
        ("source", "expected_line"),
        [
            ("# Build the FHIR client from settings\nimport os\nx = os\n", 1),
            ("def build():\n    # Build the client from settings\n    return 1\n", 2),
            ("class Registry:\n    # Hold the resolved settings\n    x = 1\n", 2),
            ("def check():\n    # Cache is empty here\n    return 1\n", 2),
        ],
        ids=["module", "function", "class", "english-operator-prose"],
    )
    def test_LeadingProseComment_FlagsViolation(
        self, source: str, expected_line: int
    ) -> None:
        violations = list(check_summary_comment_as_docstring(_SRC, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_SUMMARY_COMMENT_AS_DOCSTRING
        assert violations[0].line == expected_line

    def test_IndentedLeadingComment_ReportsItsColumn(self) -> None:
        source = "def build():\n    # Build the client now\n    return 1\n"
        violations = list(check_summary_comment_as_docstring(_SRC, source))
        assert violations[0].col == 5

    def test_ProseCommentBelowShebangAndCoding_FlagsViolation(self) -> None:
        source = (
            "#!/usr/bin/env python\n"
            "# -*- coding: utf-8 -*-\n"
            "# Configure the global registry\n"
            "import os\n"
        )
        violations = list(check_summary_comment_as_docstring(_SRC, source))
        assert len(violations) == 1
        assert violations[0].line == 3

    @pytest.mark.parametrize(
        "source",
        [
            'def build():\n    """Build the client."""\n    # Build it\n    return 1\n',
            "def build():\n    x = 1\n    # Build the client now\n    return x\n",
            "def skip():\n    # return None\n    return 1\n",
            "def assign():\n    # Total = compute(value)\n    return 1\n",
            "def note():\n    # quick note here\n    return 1\n",
            "def low():\n    # two words\n    return 1\n",
            "def directive():\n    # type: ignore the thing\n    return 1\n",
            "def build():  # Build the client now\n    return 1\n",
        ],
        ids=[
            "has-docstring",
            "deeper-comment",
            "commented-out-statement",
            "commented-out-assignment",
            "lowercase-start",
            "too-few-words",
            "directive",
            "trailing-signature-comment",
        ],
    )
    def test_NonLeadingOrNonProseComment_NoViolation(self, source: str) -> None:
        assert list(check_summary_comment_as_docstring(_SRC, source)) == []

    def test_NonPythonPath_NoViolation(self) -> None:
        source = "# Build the FHIR client from settings\nimport os\n"
        assert list(check_summary_comment_as_docstring(Path("README.md"), source)) == []

    def test_UnparseableSource_NoViolation(self) -> None:
        source = "# Build the client from settings\ndef (:\n"
        assert list(check_summary_comment_as_docstring(_SRC, source)) == []


class TestCheckFieldCommentAsDocstring:
    def test_DataclassFieldWithProseComment_FlagsViolation(self) -> None:
        source = (
            "from dataclasses import dataclass\n"
            "@dataclass\n"
            "class Patient:\n"
            "    name: str  # The full patient name\n"
        )
        violations = list(check_field_comment_as_docstring(_SRC, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_FIELD_COMMENT_AS_DOCSTRING
        assert violations[0].line == 4

    def test_MultiLineFieldValueWithTrailingComment_FlagsViolation(self) -> None:
        source = (
            "from dataclasses import dataclass, field\n"
            "@dataclass\n"
            "class Patient:\n"
            "    tags: list = field(\n"
            "        default_factory=list,\n"
            "    )  # The accumulated patient tags\n"
        )
        violations = list(check_field_comment_as_docstring(_SRC, source))
        assert len(violations) == 1
        assert violations[0].line == 4

    @pytest.mark.parametrize(
        "decorator",
        [
            "@dataclass",
            "@dataclass()",
            "@dataclasses.dataclass",
            "@dataclasses.dataclass()",
        ],
        ids=["bare", "call", "qualified", "qualified-call"],
    )
    def test_DataclassDecoratorForm_FlagsViolation(self, decorator: str) -> None:
        source = (
            "import dataclasses\n"
            "from dataclasses import dataclass\n"
            f"{decorator}\n"
            "class Patient:\n"
            "    name: str  # The full patient name\n"
        )
        violations = list(check_field_comment_as_docstring(_SRC, source))
        assert len(violations) == 1

    @pytest.mark.parametrize(
        "source",
        [
            "from dataclasses import dataclass\n"
            "@dataclass\n"
            "class Patient:\n"
            "    name: str  # The full patient name\n"
            '    """The name."""\n',
            "class Patient:\n    name: str  # The full patient name\n",
            "from dataclasses import dataclass\n"
            "@dataclass\n"
            "class Patient:\n"
            "    name: str  # noqa: E501\n",
            "from dataclasses import dataclass\n"
            "@dataclass\n"
            "class Patient:\n"
            "    name = 1  # The patient name default\n",
        ],
        ids=["has-docstring", "not-dataclass", "directive-comment", "not-annassign"],
    )
    def test_NonFiringField_NoViolation(self, source: str) -> None:
        assert list(check_field_comment_as_docstring(_SRC, source)) == []

    def test_UnparseableSource_NoViolation(self) -> None:
        source = "@dataclass\nclass (:\n    name: str  # The full patient name\n"
        assert list(check_field_comment_as_docstring(_SRC, source)) == []


class TestCheckFillerDocstringOpening:
    @pytest.mark.parametrize(
        "summary",
        [
            "This function does X.",
            "This method does X.",
            "This class holds X.",
            "This module holds rules.",
            "Helper to build it.",
            "Helper for building it.",
            "Used to compute the total.",
            "Simply returns the value.",
            "Just do the thing.",
        ],
        ids=[
            "this-function",
            "this-method",
            "this-class",
            "this-module",
            "helper-to",
            "helper-for",
            "used-to",
            "simply",
            "just",
        ],
    )
    def test_FillerOpening_FlagsViolation(self, summary: str) -> None:
        source = f'def f():\n    """{summary}"""\n    return 1\n'
        violations = list(check_filler_docstring_opening(_SRC, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_FILLER_DOCSTRING_OPENING
        assert violations[0].line == 1

    @pytest.mark.parametrize(
        ("source", "expected_line"),
        [
            ('"""This module holds rules."""\nx = 1\n', 1),
            ('class C:\n    """This class holds state."""\n    x = 1\n', 1),
        ],
        ids=["module", "class"],
    )
    def test_FillerOpeningOnNonFunctionOwner_FlagsViolation(
        self, source: str, expected_line: int
    ) -> None:
        violations = list(check_filler_docstring_opening(_SRC, source))
        assert len(violations) == 1
        assert violations[0].line == expected_line

    def test_FillerOpeningOnLaterSummaryLine_FlagsViolation(self) -> None:
        source = 'def f():\n    """\n    This function does X.\n    """\n    return 1\n'
        assert len(list(check_filler_docstring_opening(_SRC, source))) == 1

    def test_FillerOpeningIsCaseInsensitive_FlagsViolation(self) -> None:
        source = 'def f():\n    """this function does X."""\n    return 1\n'
        assert len(list(check_filler_docstring_opening(_SRC, source))) == 1

    @pytest.mark.parametrize(
        "summary",
        ["Return the count.", "Justify the layout.", "Thistle blooms early."],
        ids=["plain", "just-prefix-word", "this-prefix-word"],
    )
    def test_ContractStatingOpening_NoViolation(self, summary: str) -> None:
        source = f'def f():\n    """{summary}"""\n    return 1\n'
        assert list(check_filler_docstring_opening(_SRC, source)) == []

    def test_NoDocstring_NoViolation(self) -> None:
        source = "def f():\n    return 1\n"
        assert list(check_filler_docstring_opening(_SRC, source)) == []

    def test_UnparseableSource_NoViolation(self) -> None:
        source = 'def (:\n    """This function does X."""\n'
        assert list(check_filler_docstring_opening(_SRC, source)) == []


class TestCheckImperativeDocstringOpening:
    @pytest.mark.parametrize(
        ("summary", "expected_message_fragment"),
        [
            ("Return the lease.", "'Returns', not 'Return'"),
            ("Check whether the input is valid.", "'Checks', not 'Check'"),
            ("Apply the patch.", "'Applies', not 'Apply'"),
            ("Do the work.", "'Does', not 'Do'"),
            ("Have the value ready.", "'Has', not 'Have'"),
            ("Fetch the record.", "'Fetches', not 'Fetch'"),
            ("Finish the report.", "'Finishes', not 'Finish'"),
            ("Advance the cursor.", "'Advances', not 'Advance'"),
            ("Upsert the cursor.", "'Upserts', not 'Upsert'"),
            ("Reconcile the study.", "'Reconciles', not 'Reconcile'"),
            ("Sign the client assertion.", "'Signs', not 'Sign'"),
            ("Encrypt the payload.", "'Encrypts', not 'Encrypt'"),
            ("Decrypt the token.", "'Decrypts', not 'Decrypt'"),
            ("Hash the file contents.", "'Hashes', not 'Hash'"),
        ],
        ids=[
            "regular",
            "kept-homograph",
            "consonant-y",
            "es-suffix-o",
            "irregular",
            "es-suffix-ch",
            "es-suffix-sh",
            "added-advance",
            "added-upsert",
            "added-reconcile",
            "added-sign",
            "added-encrypt",
            "added-decrypt",
            "added-hash",
        ],
    )
    def test_ImperativeOpening_FlagsViolation(
        self, tmp_path: Path, summary: str, expected_message_fragment: str
    ) -> None:
        source = f'def f():\n    """{summary}"""\n    return 1\n'
        violations = list(check_imperative_docstring_opening(tmp_path / "x.py", source))
        assert len(violations) == 1
        assert violations[0].rule == RS_IMPERATIVE_DOCSTRING_OPENING
        assert violations[0].line == 1
        assert expected_message_fragment in violations[0].message

    def test_ConfiguredExtraVerb_FlagsViolation(self, tmp_path: Path) -> None:
        table = '[tool.repostyle]\nimperative-verbs-extra = ["Deploy"]\n'
        source = 'def f():\n    """Deploy the release."""\n'
        target = _target(tmp_path, source, table)
        violations = list(check_imperative_docstring_opening(target, source))
        assert len(violations) == 1
        assert "'Deploys', not 'Deploy'" in violations[0].message

    def test_ConfiguredExcludedVerb_NoViolation(self, tmp_path: Path) -> None:
        table = '[tool.repostyle]\nimperative-verbs-exclude = ["Check"]\n'
        source = 'def f():\n    """Check constraint on the age column."""\n'
        target = _target(tmp_path, source, table)
        assert list(check_imperative_docstring_opening(target, source)) == []

    def test_ConfiguredSingleLetterExtraVerb_DoesNotCrash(self, tmp_path: Path) -> None:
        """Conjugates a one-letter configured verb without an index error."""
        table = '[tool.repostyle]\nimperative-verbs-extra = ["y"]\n'
        source = 'def f():\n    """y the thing."""\n'
        target = _target(tmp_path, source, table)
        violations = list(check_imperative_docstring_opening(target, source))
        assert "'ys', not 'y'" in violations[0].message

    @pytest.mark.parametrize(
        ("source", "expected_line"),
        [
            ('"""Return the version string."""\nx = 1\n', 1),
            ('class C:\n    """Return the cached state."""\n    x = 1\n', 1),
        ],
        ids=["module", "class"],
    )
    def test_ImperativeOpeningOnNonFunctionOwner_FlagsViolation(
        self, tmp_path: Path, source: str, expected_line: int
    ) -> None:
        violations = list(check_imperative_docstring_opening(tmp_path / "x.py", source))
        assert len(violations) == 1
        assert violations[0].line == expected_line

    def test_ImperativeOpeningOnLaterSummaryLine_FlagsViolation(
        self, tmp_path: Path
    ) -> None:
        source = 'def f():\n    """\n    Return the count.\n    """\n    return 1\n'
        target = tmp_path / "x.py"
        assert len(list(check_imperative_docstring_opening(target, source))) == 1

    @pytest.mark.parametrize(
        "summary",
        [
            "Returns the lease held by the client.",
            "A test that returns the lease.",
            "Returned the wrong lease before this fix.",
            "List of patient records returned by the query.",
            "Partial application of the handler.",
        ],
        ids=[
            "descriptive",
            "not-first-word",
            "past-tense",
            "excluded-domain-noun",
            "excluded-not-a-verb",
        ],
    )
    def test_DescriptiveOpening_NoViolation(self, tmp_path: Path, summary: str) -> None:
        source = f'def f():\n    """{summary}"""\n    return 1\n'
        assert list(check_imperative_docstring_opening(tmp_path / "x.py", source)) == []

    def test_ImperativeOpeningIsCaseSensitive_NoViolation(self, tmp_path: Path) -> None:
        source = 'def f():\n    """return the count."""\n    return 1\n'
        assert list(check_imperative_docstring_opening(tmp_path / "x.py", source)) == []

    def test_NoDocstring_NoViolation(self, tmp_path: Path) -> None:
        source = "def f():\n    return 1\n"
        assert list(check_imperative_docstring_opening(tmp_path / "x.py", source)) == []

    def test_UnparseableSource_NoViolation(self, tmp_path: Path) -> None:
        source = 'def (:\n    """Return the count."""\n'
        assert list(check_imperative_docstring_opening(tmp_path / "x.py", source)) == []


class TestImperativeVerbConjugations:
    def test_SurveyedHomographs_StayInVerbList(self) -> None:
        """Keeps homographs a repo survey found genuinely imperative."""
        kept = {"Check", "Report", "Route", "Format", "Handle", "Set"}
        assert kept <= set(IMPERATIVE_VERB_CONJUGATIONS)

    def test_PydocstyleAcceptedHomographs_StayInVerbList(self) -> None:
        """Keeps homographs pydocstyle's list accepts with no repo survey."""
        pydocstyle_backed = {"Group", "Flag", "Filter"}
        assert pydocstyle_backed <= set(IMPERATIVE_VERB_CONJUGATIONS)

    def test_ExcludedWords_AreNotInVerbList(self) -> None:
        domain_nouns = {
            "List",
            "Query",
            "Post",
            "Test",
            "Import",
            "View",
            "Map",
            "Store",
            "Log",
            "Process",
            "Match",
        }
        not_real_verbs = {"Partial", "Rollback", "Init"}
        assert not (domain_nouns | not_real_verbs) & set(IMPERATIVE_VERB_CONJUGATIONS)

    def test_NonTrivialConjugations_KeepsOnlyIrregularAndSuffixChanges(self) -> None:
        assert NON_TRIVIAL_CONJUGATIONS["Have"] == "Has"
        assert NON_TRIVIAL_CONJUGATIONS["Fetch"] == "Fetches"
        assert "Return" not in NON_TRIVIAL_CONJUGATIONS
        assert set(NON_TRIVIAL_CONJUGATIONS) <= set(IMPERATIVE_VERB_CONJUGATIONS)


def _target(tmp_path: Path, source: str, table: str = "") -> Path:
    if table:
        (tmp_path / "pyproject.toml").write_text(table, encoding="utf-8")
    target = tmp_path / "module.py"
    target.write_text(source, encoding="utf-8")
    return target
