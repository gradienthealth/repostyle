import sys
from pathlib import Path

import pytest

from repostyle.rules import (
    RS_DOC_FILL,
    RS_DOC_SUMMARY_OVERFLOW,
    RS_DURATION_AS_TIMEDELTA,
    RS_NO_PHI_SAFE_EXC_INFO,
    RS_PORT_NO_IMPLEMENTATION,
    check_doc_fill,
    check_doc_summary_overflow,
    check_duration_as_timedelta,
    check_no_phi_safe_with_exc_info,
    check_port_no_implementation,
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
        path = Path("src/example_service/application/ports/example.py")
        violations = list(check_port_no_implementation(path, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_PORT_NO_IMPLEMENTATION
        assert token in violations[0].message

    def test_PortDocstringContractOnly_NoViolation(self) -> None:
        source = '"""Yield a lease on a pending row for the duration of the context."""'
        path = Path("src/example_service/application/ports/example.py")
        assert list(check_port_no_implementation(path, source)) == []

    def test_AdapterFileMentionsImpl_NotChecked(self) -> None:
        source = '"""Backed by sqlalchemy."""'
        path = Path("src/example_service/infrastructure/adapters/example.py")
        assert list(check_port_no_implementation(path, source)) == []

    @pytest.mark.parametrize(
        "globs_value",
        ['["contracts/*.py"]', '"contracts/*.py"'],
        ids=["list", "bare_string"],
    )
    def test_ConfiguredGlobs_CheckMatchingFile(
        self, tmp_path: Path, globs_value: str
    ) -> None:
        target = _port_scope_target(tmp_path, globs_value, "contracts/lease.py")
        violations = list(
            check_port_no_implementation(target, '"""Uses httpx under the hood."""')
        )
        assert len(violations) == 1
        assert violations[0].rule == RS_PORT_NO_IMPLEMENTATION

    def test_ConfiguredGlobs_ReplaceDefaultScope(self, tmp_path: Path) -> None:
        target = _port_scope_target(
            tmp_path, '["contracts/*.py"]', "application/ports/lease.py"
        )
        source = '"""Uses httpx under the hood."""'
        assert list(check_port_no_implementation(target, source)) == []


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
            "# curl --proxy http://proxy:3128 \\\n#     https://example.com\nx = 1",
            "# RELEASE_URI   where the workflow publishes\n"
            "# COMPOSE_DIR   where the compose file lives\nx = 1",
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
            "line_continuation",
            "column_aligned_list",
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
        # enforce, not RS035's -- the summary line itself fits.
        source = '"""Summary.\n\n' + "abcde " * 13 + 'end\n"""'
        assert list(check_doc_summary_overflow(Path("src/x.py"), source)) == []

    def test_NonPythonFile_NotChecked(self) -> None:
        source = "# " + "a" * 90
        assert list(check_doc_summary_overflow(Path("config.toml"), source)) == []

    def test_UnparseablePython_NotChecked(self) -> None:
        source = "def f(:\n" + '"""' + "a" * 90 + '"""\n'
        assert list(check_doc_summary_overflow(Path("src/x.py"), source)) == []


def _port_scope_target(tmp_path: Path, globs_value: str, relative: str) -> Path:
    """Writes a pyproject configuring `port-path-globs` and returns a path.

    The returned path sits under `tmp_path` at `relative`; the file itself is
    never written, since `check_port_no_implementation` takes the source
    separately.
    """
    (tmp_path / "pyproject.toml").write_text(
        f"[tool.repostyle]\nport-path-globs = {globs_value}\n", encoding="utf-8"
    )
    return tmp_path / relative
