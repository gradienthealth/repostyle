from pathlib import Path

import pytest

from pystyle.rules import RS_ONE_VERB_PER_CONCEPT, check_one_verb_per_concept

_SYNONYM_TABLE = '[tool.pystyle.verb-synonyms]\nfetch = ["retrieve", "load"]\n'


class TestCheckOneVerbPerConcept:
    @pytest.mark.parametrize(
        "source",
        [
            "def retrieve_patient():\n    pass\n",
            "def load_bundle():\n    pass\n",
            "async def retrieve_token():\n    pass\n",
            "class Store:\n    def retrieve_row(self):\n        pass\n",
            "def retrieve():\n    pass\n",
        ],
        ids=["function", "second_synonym", "async", "method", "bare_verb"],
    )
    def test_BannedSynonymVerb_FlagsViolation(
        self, tmp_path: Path, source: str
    ) -> None:
        target = _target(tmp_path, "src/pkg/m.py", source)
        violations = list(check_one_verb_per_concept(target, source))
        assert len(violations) == 1
        assert violations[0].rule == RS_ONE_VERB_PER_CONCEPT

    def test_SeveralSynonyms_FlagsEach(self, tmp_path: Path) -> None:
        source = "def retrieve_a():\n    pass\n\n\ndef load_b():\n    pass\n"
        target = _target(tmp_path, "src/pkg/m.py", source)
        violations = list(check_one_verb_per_concept(target, source))
        assert [violation.line for violation in violations] == [1, 5]

    @pytest.mark.parametrize(
        "source",
        [
            "def fetch_patient():\n    pass\n",
            "def parse_bundle():\n    pass\n",
        ],
        ids=["canonical_verb", "unrelated_verb"],
    )
    def test_CanonicalOrUnrelatedVerb_NoViolation(
        self, tmp_path: Path, source: str
    ) -> None:
        target = _target(tmp_path, "src/pkg/m.py", source)
        assert list(check_one_verb_per_concept(target, source)) == []

    @pytest.mark.parametrize(
        "source",
        [
            "def retrieves_data():\n    pass\n",
            "def loader():\n    pass\n",
        ],
        ids=["synonym_prefix_verb", "synonym_prefix_noun"],
    )
    def test_SynonymIsMerelyAPrefix_NoViolation(
        self, tmp_path: Path, source: str
    ) -> None:
        target = _target(tmp_path, "src/pkg/m.py", source)
        assert list(check_one_verb_per_concept(target, source)) == []

    def test_NoVerbSynonymsTable_NoViolation(self, tmp_path: Path) -> None:
        source = "def retrieve_patient():\n    pass\n"
        target = _target(
            tmp_path, "src/pkg/m.py", source, table="[tool.other]\nx = 1\n"
        )
        assert list(check_one_verb_per_concept(target, source)) == []

    @pytest.mark.parametrize(
        "relative",
        ["tests/m.py", "conftest.py"],
        ids=["test_dir", "conftest"],
    )
    def test_SkippedFile_NoViolation(self, tmp_path: Path, relative: str) -> None:
        source = "def retrieve_patient():\n    pass\n"
        target = _target(tmp_path, relative, source)
        assert list(check_one_verb_per_concept(target, source)) == []


def _target(
    tmp_path: Path, relative: str, source: str, table: str = _SYNONYM_TABLE
) -> Path:
    (tmp_path / "pyproject.toml").write_text(table, encoding="utf-8")
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")
    return target
