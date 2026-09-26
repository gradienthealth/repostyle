import sys
from pathlib import Path

import pytest

from repostyle.rules import (
    RS_GCP_BARE_IDENTIFIER,
    check_gcp_bare_identifier,
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


class TestCheckGCPBareIdentifier:
    @pytest.mark.parametrize(
        ("source", "name"),
        [
            ("def f(project: str): ...", "project"),
            ("def f(bucket: str): ...", "bucket"),
            ("def f(dataset: str): ...", "dataset"),
            ("def f(topic: str | None): ...", "topic"),
            ("def f(subscription: Optional[str]): ...", "subscription"),
            ("def f(project: typing.Optional[str]): ...", "project"),
            ('def f(instance: "str"): ...', "instance"),
            ("class C:\n    def m(self, project: str): ...", "project"),
            ("async def f(dataset: str): ...", "dataset"),
            ("def f(*, dataset: str): ...", "dataset"),
        ],
        ids=[
            "project",
            "bucket",
            "dataset",
            "union-optional",
            "optional-subscript",
            "qualified-optional",
            "forward-ref",
            "method-parameter",
            "async-function",
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

    def test_TwoBareParams_FlagsEach(self) -> None:
        source = "def grant(project: str, bucket: str) -> None: ..."
        violations = list(check_gcp_bare_identifier(Path("src/x.py"), source))
        assert [v.message.split("'")[1] for v in violations] == ["project", "bucket"]

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

    def test_NonPythonFile_NotChecked(self) -> None:
        source = "def f(project: str): ..."
        assert list(check_gcp_bare_identifier(Path("notes.md"), source)) == []
