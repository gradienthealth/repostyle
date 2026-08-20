from pathlib import Path

import pytest

from repostyle.rules import (
    check_acronym_casing_in_comments,
    check_acronym_casing_in_docstrings,
    check_comment_terminal_punctuation,
    check_disfavored_gcp_term_in_comments,
    check_disfavored_gcp_term_in_docstrings,
    check_double_space_after_period,
    check_nonstandard_dash_in_comments,
    check_nonstandard_dash_in_docstrings,
    fix_acronym_casing_in_comments,
    fix_acronym_casing_in_docstrings,
    fix_comment_terminal_punctuation,
    fix_disfavored_gcp_term_in_comments,
    fix_disfavored_gcp_term_in_docstrings,
    fix_docstring_section_alias,
    fix_docstring_terminal_punctuation,
    fix_double_backticks,
    fix_double_space_in_comments,
    fix_double_space_in_docstrings,
    fix_nonstandard_dash_in_comments,
    fix_nonstandard_dash_in_docstrings,
)
from repostyle.runner import fix_path

_PY = Path("src/x.py")
_MD = Path("README.md")


class TestFixDocstringSectionAlias:
    def test_AliasHeaders_RewriteToCanonical(self) -> None:
        source = (
            'def f(x):\n    """Do the thing.\n\n    Arguments:\n'
            "        x: An x.\n\n    Return:\n"
            '        The thing.\n    """\n'
        )
        expected = (
            'def f(x):\n    """Do the thing.\n\n    Args:\n'
            "        x: An x.\n\n    Returns:\n"
            '        The thing.\n    """\n'
        )
        assert fix_docstring_section_alias(_PY, source) == expected

    def test_LineSuppressed_LeavesHeader(self) -> None:
        source = (
            'def f(x):\n    """Do the thing.\n\n    Arguments:\n'
            '        x: An x.\n    """\n'
        )
        assert (
            fix_docstring_section_alias(_PY, source, skip_lines=frozenset({4}))
            == source
        )

    def test_CanonicalHeaders_ReturnsSourceUnchanged(self) -> None:
        source = (
            'def f(x):\n    """Do the thing.\n\n    Args:\n        x: An x.\n    """\n'
        )
        assert fix_docstring_section_alias(_PY, source) == source


class TestFixDoubleBackticks:
    def test_DocstringDoubleBackticks_RewriteToSingle(self) -> None:
        source = 'def f():\n    """Use ``dict`` here."""\n'
        assert fix_double_backticks(_PY, source) == (
            'def f():\n    """Use `dict` here."""\n'
        )

    def test_MarkdownProse_RewriteToSingle(self) -> None:
        assert fix_double_backticks(_MD, "See ``X`` now.\n") == "See `X` now.\n"

    def test_MarkdownFencedBlock_LeftUntouched(self) -> None:
        source = "Use ``x``.\n\n```\ncode ``y``\n```\n"
        assert fix_double_backticks(_MD, source) == "Use `x`.\n\n```\ncode ``y``\n```\n"

    def test_TripleBackticks_LeftUntouched(self) -> None:
        source = 'def f():\n    """A ```fence``` token."""\n'
        assert fix_double_backticks(_PY, source) == source

    def test_OwnerLineSuppressed_LeavesDocstring(self) -> None:
        source = 'def f():  # style: ignore[RS005]\n    """Use ``dict``."""\n'
        assert fix_double_backticks(_PY, source, frozenset({1})) == source

    def test_NoDoubleBackticks_ReturnsSourceUnchanged(self) -> None:
        source = 'def f():\n    """Use `dict` here."""\n'
        assert fix_double_backticks(_PY, source) == source


class TestFixDocstringTerminalPunctuation:
    def test_SingleLineSummary_AppendsPeriodBeforeQuote(self) -> None:
        assert fix_docstring_terminal_punctuation(_PY, '"""Resolve the lease"""\n') == (
            '"""Resolve the lease."""\n'
        )

    def test_WrappedBulletContinuation_LeftUntouched(self) -> None:
        source = (
            'def f():\n    """Do it.\n\n'
            "    - a wrapped bullet item whose continuation\n"
            "      line carries no terminal mark\n"
            '    """\n'
        )
        assert fix_docstring_terminal_punctuation(_PY, source) == source

    def test_BodyParagraph_AppendsPeriodOnLastLine(self) -> None:
        source = 'def f():\n    """Do it.\n\n    The body has no mark\n    """\n'
        assert fix_docstring_terminal_punctuation(_PY, source) == (
            'def f():\n    """Do it.\n\n    The body has no mark.\n    """\n'
        )

    def test_SectionEntry_AppendsPeriod(self) -> None:
        source = (
            'def f(a):\n    """Summary.\n\n    Args:\n        a: the thing\n    """\n'
        )
        assert fix_docstring_terminal_punctuation(_PY, source) == (
            'def f(a):\n    """Summary.\n\n    Args:\n        a: the thing.\n    """\n'
        )

    def test_UnitEndingInCloser_AppendsAfterCloser(self) -> None:
        source = 'def f():\n    """See the note (here)"""\n'
        assert fix_docstring_terminal_punctuation(_PY, source) == (
            'def f():\n    """See the note (here)."""\n'
        )

    def test_NonAsciiClosingLine_InsertsBeforeQuoteNotPastIt(self) -> None:
        source = 'def f():\n    """Résumé café text"""\n'
        assert fix_docstring_terminal_punctuation(_PY, source) == (
            'def f():\n    """Résumé café text."""\n'
        )

    def test_LineSuppressed_LeavesUnit(self) -> None:
        source = '"""Resolve the lease"""\n'
        assert fix_docstring_terminal_punctuation(_PY, source, frozenset({1})) == source

    def test_AlreadyTerminated_ReturnsSourceUnchanged(self) -> None:
        source = '"""Resolve the lease."""\n'
        assert fix_docstring_terminal_punctuation(_PY, source) == source


class TestFixCommentTerminalPunctuation:
    def test_ProseBlockMissingMark_AppendsPeriod(self) -> None:
        source = "# This is prose spanning\n# two lines here\nx = 1\n"
        assert fix_comment_terminal_punctuation(_PY, source) == (
            "# This is prose spanning\n# two lines here.\nx = 1\n"
        )

    def test_TrailingFragmentWithPeriod_RemovesTrailingPeriod(self) -> None:
        source = "x = 1  # Frobnicate the widget here.\n"
        assert fix_comment_terminal_punctuation(_PY, source) == (
            "x = 1  # Frobnicate the widget here\n"
        )

    def test_FragmentPeriodBeforeCloser_DropsPeriodKeepsCloser(self) -> None:
        source = "x = 1  # Frobnicate the widget (here.)\n"
        fixed = fix_comment_terminal_punctuation(_PY, source)
        assert fixed == "x = 1  # Frobnicate the widget (here)\n"
        assert list(check_comment_terminal_punctuation(_PY, fixed)) == []

    def test_LineSuppressed_LeavesComment(self) -> None:
        source = "x = 1  # Frobnicate the widget here.\n"
        assert fix_comment_terminal_punctuation(_PY, source, frozenset({1})) == source

    def test_YamlComment_RemovesTrailingPeriod(self) -> None:
        source = "k: v  # Frobnicate the widget here.\n"
        assert fix_comment_terminal_punctuation(Path("c.yaml"), source) == (
            "k: v  # Frobnicate the widget here\n"
        )

    def test_MarkdownPath_ReturnsSourceUnchanged(self) -> None:
        assert (
            fix_comment_terminal_punctuation(_MD, "# Title here\n") == "# Title here\n"
        )


class TestFixAcronymCasingInDocstrings:
    def test_MiscasedAcronyms_RecaseToCanonical(self) -> None:
        source = 'def f():\n    """The ipv6 and Nat and IPV6 here."""\n'
        assert fix_acronym_casing_in_docstrings(_PY, source) == (
            'def f():\n    """The IPv6 and NAT and IPv6 here."""\n'
        )

    def test_FixedDocstring_LeavesNoRemainingViolation(self) -> None:
        source = 'def f():\n    """Parses the ipv6 Nat json path."""\n'
        fixed = fix_acronym_casing_in_docstrings(_PY, source)
        assert list(check_acronym_casing_in_docstrings(_PY, fixed)) == []

    def test_LineSuppressed_LeavesUnit(self) -> None:
        source = 'def f():\n    """The ipv6 case."""\n'
        assert fix_acronym_casing_in_docstrings(_PY, source, frozenset({2})) == source

    def test_AlreadyCanonical_ReturnsSourceUnchanged(self) -> None:
        source = 'def f():\n    """The IPv6 and NAT case."""\n'
        assert fix_acronym_casing_in_docstrings(_PY, source) == source


class TestFixAcronymCasingInComments:
    def test_MiscasedAcronyms_RecaseToCanonical(self) -> None:
        source = "# routes ipv6 through the Nat gateway\nx = 1\n"
        assert fix_acronym_casing_in_comments(_PY, source) == (
            "# routes IPv6 through the NAT gateway\nx = 1\n"
        )

    def test_TrailingComment_RecasesInPlace(self) -> None:
        source = "x = 1  # the ipv6 address\n"
        assert fix_acronym_casing_in_comments(_PY, source) == (
            "x = 1  # the IPv6 address\n"
        )

    def test_FixedComment_LeavesNoRemainingViolation(self) -> None:
        source = "# handles ipv6 and the Nat gateway\nx = 1\n"
        fixed = fix_acronym_casing_in_comments(_PY, source)
        assert list(check_acronym_casing_in_comments(_PY, fixed)) == []

    def test_YamlComment_RecasesInPlace(self) -> None:
        source = "k: v  # routes ipv6 traffic\n"
        assert fix_acronym_casing_in_comments(Path("c.yaml"), source) == (
            "k: v  # routes IPv6 traffic\n"
        )

    def test_MarkdownPath_ReturnsSourceUnchanged(self) -> None:
        assert fix_acronym_casing_in_comments(_MD, "# ipv6\n") == "# ipv6\n"


class TestFixGCPProductNameInDocstrings:
    def test_DisfavoredTerms_RewriteToPreferred(self) -> None:
        source = 'def f():\n    """Wires PubSub to Big Query via GCP."""\n'
        assert fix_disfavored_gcp_term_in_docstrings(_PY, source) == (
            'def f():\n    """Wires Pub/Sub to BigQuery via Google Cloud."""\n'
        )

    def test_FixedDocstring_LeavesNoRemainingViolation(self) -> None:
        source = 'def f():\n    """Uploads to a GCS bucket in GCP."""\n'
        fixed = fix_disfavored_gcp_term_in_docstrings(_PY, source)
        assert list(check_disfavored_gcp_term_in_docstrings(_PY, fixed)) == []

    def test_LineSuppressed_LeavesUnit(self) -> None:
        source = 'def f():\n    """The GCS bucket."""\n'
        assert (
            fix_disfavored_gcp_term_in_docstrings(_PY, source, frozenset({2})) == source
        )

    def test_AlreadyPreferred_ReturnsSourceUnchanged(self) -> None:
        source = 'def f():\n    """The Cloud Storage bucket in Google Cloud."""\n'
        assert fix_disfavored_gcp_term_in_docstrings(_PY, source) == source

    def test_OneLineDef_RewritesDocstringNotSignature(self) -> None:
        source = 'def f(gcp): """Uses GCS."""\n'
        assert fix_disfavored_gcp_term_in_docstrings(_PY, source) == (
            'def f(gcp): """Uses Cloud Storage."""\n'
        )


class TestFixGCPProductNameInComments:
    def test_DisfavoredTerms_RewriteToPreferred(self) -> None:
        source = "# stages the study in a GCS bucket on GCP\nx = 1\n"
        assert fix_disfavored_gcp_term_in_comments(_PY, source) == (
            "# stages the study in a Cloud Storage bucket on Google Cloud\nx = 1\n"
        )

    def test_TrailingComment_RewritesInPlace(self) -> None:
        source = "x = 1  # the GCS staging bucket\n"
        assert fix_disfavored_gcp_term_in_comments(_PY, source) == (
            "x = 1  # the Cloud Storage staging bucket\n"
        )

    def test_FixedComment_LeavesNoRemainingViolation(self) -> None:
        source = "# stages in GCS on GCP\nx = 1\n"
        fixed = fix_disfavored_gcp_term_in_comments(_PY, source)
        assert list(check_disfavored_gcp_term_in_comments(_PY, fixed)) == []

    def test_YamlComment_RewritesInPlace(self) -> None:
        source = "k: v  # the GCS staging bucket\n"
        assert fix_disfavored_gcp_term_in_comments(Path("c.yaml"), source) == (
            "k: v  # the Cloud Storage staging bucket\n"
        )

    def test_MarkdownPath_ReturnsSourceUnchanged(self) -> None:
        assert fix_disfavored_gcp_term_in_comments(_MD, "# GCS\n") == "# GCS\n"


class TestFixNonstandardDash:
    @pytest.mark.parametrize(
        ("bad", "good"),
        [
            ("a — b", "a -- b"),
            ("a—b", "a -- b"),
            ("a – b", "a -- b"),  # noqa: RUF001
            ("a - b", "a -- b"),
            ("a--b", "a -- b"),
        ],
        ids=[
            "spaced-em-dash",
            "glued-em-dash",
            "spaced-en-dash",
            "spaced-hyphen",
            "glued-double-hyphen",
        ],
    )
    def test_DocstringForm_RewritesToStandard(self, bad: str, good: str) -> None:
        source = f'def f():\n    """Returns {bad} now."""\n'
        assert fix_nonstandard_dash_in_docstrings(_PY, source) == (
            f'def f():\n    """Returns {good} now."""\n'
        )

    def test_TwoFaultsOneLine_RewritesRightToLeft(self) -> None:
        source = 'def f():\n    """Runs a — b — c now."""\n'
        assert fix_nonstandard_dash_in_docstrings(_PY, source) == (
            'def f():\n    """Runs a -- b -- c now."""\n'
        )

    def test_FixedDocstring_LeavesNoRemainingViolation(self) -> None:
        source = 'def f():\n    """Returns a — b now."""\n'
        fixed = fix_nonstandard_dash_in_docstrings(_PY, source)
        assert list(check_nonstandard_dash_in_docstrings(_PY, fixed)) == []

    def test_SuppressedLine_LeftUntouched(self) -> None:
        source = 'def f():\n    """Returns a — b now."""\n'
        assert fix_nonstandard_dash_in_docstrings(_PY, source, frozenset({2})) == source

    def test_CommentForm_RewritesInPlace(self) -> None:
        source = "# tuned — carefully\nx = 1\n"
        fixed = fix_nonstandard_dash_in_comments(_PY, source)
        assert fixed == "# tuned -- carefully\nx = 1\n"
        assert list(check_nonstandard_dash_in_comments(_PY, fixed)) == []

    def test_YamlComment_RewritesInPlace(self) -> None:
        source = "# tuned — carefully\nk: v\n"
        fixed = fix_nonstandard_dash_in_comments(Path("c.yaml"), source)
        assert fixed == "# tuned -- carefully\nk: v\n"

    def test_StandardDash_ReturnsSourceUnchanged(self) -> None:
        source = 'def f():\n    """Returns a -- b now."""\n'
        assert fix_nonstandard_dash_in_docstrings(_PY, source) == source


class TestFixPath:
    def test_EnabledFixers_ComposeOnOneFile(self, tmp_path: Path) -> None:
        source = (
            'def f():\n    """Use ``dict`` here\n\n'
            '    The body line has no mark\n    """\n'
        )
        target = _write_project(tmp_path, source, '["RS005", "RS009", "RS030"]')
        assert fix_path(target, {"RS005", "RS009", "RS030"}) is True
        assert target.read_text(encoding="utf-8") == (
            'def f():\n    """Use `dict` here.\n\n'
            '    The body line has no mark.\n    """\n'
        )

    def test_DashRewriteThenReflow_ComposeInOrder(self, tmp_path: Path) -> None:
        # The dash rewrite lengthens the 79-column body line to 80, so the
        # final wrap proves the reflow ran after it.
        source = (
            'def f():\n    """Do it.\n\n'
            "    resolves the config — falling back to the defaults when the "
            'file is absent.\n    """\n'
        )
        target = _write_project(tmp_path, source, '["RS009", "RS054"]')
        assert fix_path(target, {"RS009", "RS054"}) is True
        assert target.read_text(encoding="utf-8") == (
            'def f():\n    """Do it.\n\n'
            "    resolves the config -- falling back to the defaults when the "
            "file is\n    absent.\n"
            '    """\n'
        )

    def test_OnlyOneRuleEnabled_OtherFixersSkipped(self, tmp_path: Path) -> None:
        source = 'def f():\n    """Use ``dict`` here"""\n'
        target = _write_project(tmp_path, source, '["RS005"]')
        fix_path(target, {"RS005"})
        assert target.read_text(encoding="utf-8") == (
            'def f():\n    """Use `dict` here"""\n'
        )

    def test_AcronymCasingRule_RecasesDocstringAndComment(self, tmp_path: Path) -> None:
        source = 'def f():\n    # routes ipv6\n    """The Nat gateway."""\n'
        target = _write_project(tmp_path, source, '["RS049"]')
        assert fix_path(target, {"RS049"}) is True
        assert target.read_text(encoding="utf-8") == (
            'def f():\n    # routes IPv6\n    """The NAT gateway."""\n'
        )

    def test_GcpTermRule_RewritesDocstringAndComment(self, tmp_path: Path) -> None:
        source = 'def f():\n    # stages in GCS\n    """Runs on GCP."""\n'
        target = _write_project(tmp_path, source, '["RS050"]')
        assert fix_path(target, {"RS050"}) is True
        assert target.read_text(encoding="utf-8") == (
            'def f():\n    # stages in Cloud Storage\n    """Runs on Google Cloud."""\n'
        )

    def test_MarkdownFile_FixesBackticksOnly(self, tmp_path: Path) -> None:
        target = _write_project(tmp_path, "See ``X``.\n", '["RS005"]', name="README.md")
        assert fix_path(target, {"RS005"}) is True
        assert target.read_text(encoding="utf-8") == "See `X`.\n"

    def test_FileLevelIgnore_LeavesFileUntouched(self, tmp_path: Path) -> None:
        source = '# style: ignore-file\ndef f():\n    """Use ``dict``"""\n'
        target = _write_project(tmp_path, source, '["RS005", "RS030"]')
        assert fix_path(target, {"RS005", "RS030"}) is False
        assert target.read_text(encoding="utf-8") == source

    def test_NoEnabledFixableRule_NoOp(self, tmp_path: Path) -> None:
        source = 'def f():\n    """Use ``dict``"""\n'
        target = _write_project(tmp_path, source, '["RS001"]')
        assert fix_path(target, {"RS001"}) is False
        assert target.read_text(encoding="utf-8") == source

    def test_NonSourceSuffix_NoOp(self, tmp_path: Path) -> None:
        target = _write_project(tmp_path, "See ``X``.\n", '["RS005"]', name="data.txt")
        assert fix_path(target, {"RS005"}) is False


class TestFixDoubleSpaceInDocstrings:
    def test_SingleLineDocstring_CollapsesToOne(self) -> None:
        source = 'def f():\n    """First.  Second."""\n'
        assert fix_double_space_in_docstrings(_PY, source) == (
            'def f():\n    """First. Second."""\n'
        )

    def test_MultiLineDocstring_CollapsesBody(self) -> None:
        source = 'def f():\n    """Summary.\n\n    One.  Two.\n    """\n'
        assert fix_double_space_in_docstrings(_PY, source) == (
            'def f():\n    """Summary.\n\n    One. Two.\n    """\n'
        )

    def test_ThreeSpaces_CollapsesToOne(self) -> None:
        source = 'def f():\n    """Foo.   Bar."""\n'
        assert fix_double_space_in_docstrings(_PY, source) == (
            'def f():\n    """Foo. Bar."""\n'
        )

    def test_NoDoubleSpace_ReturnsUnchanged(self) -> None:
        source = 'def f():\n    """One. Two."""\n'
        assert fix_double_space_in_docstrings(_PY, source) == source

    def test_NonPythonFile_ReturnsUnchanged(self) -> None:
        source = "# First.  Second.\n"
        assert fix_double_space_in_docstrings(Path("config.yaml"), source) == source

    def test_SuppressedLine_LeavesUntouched(self) -> None:
        source = 'def f():\n    """First.  Second."""\n'
        assert fix_double_space_in_docstrings(_PY, source, frozenset({2})) == source

    def test_ExclamationMark_CollapsesToOne(self) -> None:
        source = 'def f():\n    """Warning!  Do not proceed."""\n'
        assert fix_double_space_in_docstrings(_PY, source) == (
            'def f():\n    """Warning! Do not proceed."""\n'
        )

    def test_QuestionMark_CollapsesToOne(self) -> None:
        source = 'def f():\n    """Ready?  Let us check."""\n'
        assert fix_double_space_in_docstrings(_PY, source) == (
            'def f():\n    """Ready? Let us check."""\n'
        )

    def test_RoundTrip_NoCheckViolationsAfterFix(self) -> None:
        source = 'def f():\n    """One.  Two.  Three."""\n'
        fixed = fix_double_space_in_docstrings(_PY, source)
        violations = [
            v for v in check_double_space_after_period(_PY, fixed) if v.rule == "RS061"
        ]
        assert violations == []


class TestFixDoubleSpaceInComments:
    def test_PythonComment_CollapsesToOne(self) -> None:
        source = "# First.  Second.\n"
        assert fix_double_space_in_comments(_PY, source) == "# First. Second.\n"

    def test_TrailingComment_FixesCommentOnly(self) -> None:
        source = 'x = "a.  b"  # First.  Second.\n'
        assert fix_double_space_in_comments(_PY, source) == (
            'x = "a.  b"  # First. Second.\n'
        )

    def test_YamlComment_CollapsesToOne(self) -> None:
        source = "# First.  Second.\n"
        assert fix_double_space_in_comments(Path("config.yaml"), source) == (
            "# First. Second.\n"
        )

    def test_TomlComment_CollapsesToOne(self) -> None:
        source = "# First.  Second.\n"
        assert fix_double_space_in_comments(Path("config.toml"), source) == (
            "# First. Second.\n"
        )

    def test_ShellComment_CollapsesToOne(self) -> None:
        source = "# First.  Second.\n"
        assert fix_double_space_in_comments(Path("script.sh"), source) == (
            "# First. Second.\n"
        )

    def test_NoDoubleSpace_ReturnsUnchanged(self) -> None:
        source = "# First. Second.\n"
        assert fix_double_space_in_comments(_PY, source) == source

    def test_SuppressedLine_LeavesUntouched(self) -> None:
        source = "# First.  Second.\n"
        assert fix_double_space_in_comments(_PY, source, frozenset({1})) == source

    def test_UnsupportedSuffix_ReturnsUnchanged(self) -> None:
        source = "# First.  Second.\n"
        assert fix_double_space_in_comments(Path("data.txt"), source) == source


def _write_project(
    tmp_path: Path, source: str, select: str, name: str = "x.py"
) -> Path:
    (tmp_path / "pyproject.toml").write_text(
        f"[tool.repostyle]\nselect = {select}\n", encoding="utf-8"
    )
    target = tmp_path / name
    target.write_text(source, encoding="utf-8")
    return target
