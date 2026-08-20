from pathlib import Path

from repostyle import baseline
from repostyle.baseline import Baseline
from repostyle.rules import (
    RS_ACRONYM_CASING,
    RS_BANNED_ABBREVIATION,
    RS_DISCOURAGED_CLASS_SUFFIX,
    Violation,
)


class TestBuild:
    def test_FindingsAcrossRules_CountsEachRuleSeparately(self, tmp_path: Path) -> None:
        target = tmp_path / "pkg" / "x.py"
        target.parent.mkdir()
        findings = {
            target: [
                _violation(1, RS_ACRONYM_CASING),
                _violation(4, RS_ACRONYM_CASING),
                _violation(9, RS_BANNED_ABBREVIATION),
            ]
        }
        built = baseline.build(findings, tmp_path, frozenset({RS_ACRONYM_CASING}))
        assert built.counts == {
            "pkg/x.py": {RS_ACRONYM_CASING: 2, RS_BANNED_ABBREVIATION: 1}
        }

    def test_CleanFile_IsAbsentFromTheRecord(self, tmp_path: Path) -> None:
        built = baseline.build({tmp_path / "x.py": []}, tmp_path, frozenset())
        assert built.counts == {}


class TestSaveAndLoad:
    def test_WrittenBaseline_RoundTrips(self, tmp_path: Path) -> None:
        written = Baseline(
            rules=frozenset({RS_ACRONYM_CASING}),
            counts={"x.py": {RS_ACRONYM_CASING: 3}},
        )
        path = tmp_path / "b.json"
        baseline.save(path, written)
        assert baseline.load(path) == written

    def test_MalformedFile_LoadsAsNone(self, tmp_path: Path) -> None:
        path = tmp_path / "b.json"
        path.write_text("{not json", encoding="utf-8")
        assert baseline.load(path) is None

    def test_UnknownSchema_LoadsAsNone(self, tmp_path: Path) -> None:
        path = tmp_path / "b.json"
        path.write_text('{"schema": 99, "rules": [], "counts": {}}', encoding="utf-8")
        assert baseline.load(path) is None


class TestFilterBaselined:
    def test_FindingsWithinTheCount_AreDropped(self, tmp_path: Path) -> None:
        target = tmp_path / "x.py"
        grandfathered = Baseline(
            rules=frozenset({RS_ACRONYM_CASING}),
            counts={"x.py": {RS_ACRONYM_CASING: 2}},
        )
        violations = [
            _violation(1, RS_ACRONYM_CASING),
            _violation(2, RS_ACRONYM_CASING),
        ]
        assert (
            baseline.filter_baselined(target, violations, grandfathered, tmp_path) == []
        )

    def test_FindingBeyondTheCount_IsReported(self, tmp_path: Path) -> None:
        target = tmp_path / "x.py"
        grandfathered = Baseline(
            rules=frozenset({RS_ACRONYM_CASING}),
            counts={"x.py": {RS_ACRONYM_CASING: 1}},
        )
        violations = [
            _violation(1, RS_ACRONYM_CASING),
            _violation(7, RS_ACRONYM_CASING),
        ]
        kept = baseline.filter_baselined(target, violations, grandfathered, tmp_path)
        assert kept == [_violation(7, RS_ACRONYM_CASING)]

    def test_UnrecordedRule_IsReportedInFull(self, tmp_path: Path) -> None:
        target = tmp_path / "x.py"
        grandfathered = Baseline(
            rules=frozenset({RS_ACRONYM_CASING}),
            counts={"x.py": {RS_ACRONYM_CASING: 5}},
        )
        violations = [_violation(1, RS_BANNED_ABBREVIATION)]
        kept = baseline.filter_baselined(target, violations, grandfathered, tmp_path)
        assert kept == violations

    def test_UnrecordedFile_IsReportedInFull(self, tmp_path: Path) -> None:
        grandfathered = Baseline(rules=frozenset(), counts={})
        violations = [_violation(1, RS_ACRONYM_CASING)]
        kept = baseline.filter_baselined(
            tmp_path / "other.py", violations, grandfathered, tmp_path
        )
        assert kept == violations


class TestRefresh:
    def test_FixedFinding_LowersTheCountPermanently(self) -> None:
        existing = Baseline(
            rules=frozenset({RS_ACRONYM_CASING}),
            counts={"x.py": {RS_ACRONYM_CASING: 4}},
        )
        current = Baseline(
            rules=frozenset({RS_ACRONYM_CASING}),
            counts={"x.py": {RS_ACRONYM_CASING: 1}},
        )
        assert baseline.refresh(existing, current, {"x.py"}).counts == {
            "x.py": {RS_ACRONYM_CASING: 1}
        }

    def test_NewFindingOfAKnownRule_IsNotGrandfathered(self) -> None:
        existing = Baseline(
            rules=frozenset({RS_ACRONYM_CASING}),
            counts={"x.py": {RS_ACRONYM_CASING: 1}},
        )
        current = Baseline(
            rules=frozenset({RS_ACRONYM_CASING}),
            counts={"x.py": {RS_ACRONYM_CASING: 6}},
        )
        assert baseline.refresh(existing, current, {"x.py"}).counts == {
            "x.py": {RS_ACRONYM_CASING: 1}
        }

    def test_RuleTheBaselinePredates_IsGrandfatheredInFull(self) -> None:
        existing = Baseline(
            rules=frozenset({RS_ACRONYM_CASING}),
            counts={"x.py": {RS_ACRONYM_CASING: 1}},
        )
        current = Baseline(
            rules=frozenset({RS_ACRONYM_CASING, RS_DISCOURAGED_CLASS_SUFFIX}),
            counts={"x.py": {RS_ACRONYM_CASING: 1, RS_DISCOURAGED_CLASS_SUFFIX: 9}},
        )
        refreshed = baseline.refresh(existing, current, {"x.py"})
        assert refreshed.counts == {
            "x.py": {RS_ACRONYM_CASING: 1, RS_DISCOURAGED_CLASS_SUFFIX: 9}
        }
        assert RS_DISCOURAGED_CLASS_SUFFIX in refreshed.rules

    def test_FileWithNothingLeft_LeavesTheRecord(self) -> None:
        existing = Baseline(
            rules=frozenset({RS_ACRONYM_CASING}),
            counts={"x.py": {RS_ACRONYM_CASING: 2}},
        )
        current = Baseline(rules=frozenset({RS_ACRONYM_CASING}), counts={})
        assert baseline.refresh(existing, current, {"x.py"}).counts == {}


class TestRefreshScope:
    def test_UnscannedFile_KeepsItsCounts(self) -> None:
        existing = Baseline(
            rules=frozenset({RS_ACRONYM_CASING}),
            counts={
                "a/x.py": {RS_ACRONYM_CASING: 1},
                "b/y.py": {RS_ACRONYM_CASING: 1},
            },
        )
        current = Baseline(
            rules=frozenset({RS_ACRONYM_CASING}),
            counts={"a/x.py": {RS_ACRONYM_CASING: 1}},
        )
        refreshed = baseline.refresh(existing, current, {"a/x.py"})
        assert refreshed.counts == {
            "a/x.py": {RS_ACRONYM_CASING: 1},
            "b/y.py": {RS_ACRONYM_CASING: 1},
        }

    def test_ScannedFileNowClean_LosesItsCounts(self) -> None:
        existing = Baseline(
            rules=frozenset({RS_ACRONYM_CASING}),
            counts={"a/x.py": {RS_ACRONYM_CASING: 1}},
        )
        current = Baseline(rules=frozenset({RS_ACRONYM_CASING}), counts={})
        assert baseline.refresh(existing, current, {"a/x.py"}).counts == {}


def _violation(line: int, rule: str) -> Violation:
    return Violation(line=line, col=1, rule=rule, message="m")
