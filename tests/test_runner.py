from pathlib import Path

import pytest

from repostyle.rules import (
    ALL_RULE_IDS,
    RS_ACRONYM_CASING,
    RS_DISCOURAGED_CLASS_SUFFIX,
    RS_DOC_FILL,
    RS_NO_DOUBLE_BACKTICKS,
    RS_SHOULD_BE_PRIVATE,
    Severity,
    severity_of,
)
from repostyle.runner import (
    expand_paths,
    find_pyproject,
    fix_path,
    lint_package,
    lint_path,
    lint_paths,
    load_config,
    resolve_enabled_rules,
    resolve_enabled_rules_for_paths,
)

_UNDERWRAPPED_DOCSTRING = 'def f():\n    """Summary.\n\n    aaa\n    bbb\n    """\n'

_ACRONYM_AND_SUFFIX_SOURCE = "class FhirManager: ...\n"


class TestResolveEnabledRules:
    @pytest.mark.parametrize("config", [None, {}], ids=["missing_table", "empty_table"])
    def test_MissingOrEmptyConfig_EnablesAllRules(self, config: dict | None) -> None:
        assert resolve_enabled_rules(config) == set(ALL_RULE_IDS)

    def test_SelectSubset_EnablesOnlyThose(self) -> None:
        config = {"select": [RS_ACRONYM_CASING, RS_DISCOURAGED_CLASS_SUFFIX]}
        assert resolve_enabled_rules(config) == {
            RS_ACRONYM_CASING,
            RS_DISCOURAGED_CLASS_SUFFIX,
        }

    def test_Ignore_RemovesRuleFromAll(self) -> None:
        enabled = resolve_enabled_rules({"ignore": [RS_ACRONYM_CASING]})
        assert RS_ACRONYM_CASING not in enabled
        assert enabled == set(ALL_RULE_IDS) - {RS_ACRONYM_CASING}

    def test_SelectThenIgnore_AppliesDifference(self) -> None:
        config = {
            "select": [RS_ACRONYM_CASING, RS_DISCOURAGED_CLASS_SUFFIX],
            "ignore": [RS_DISCOURAGED_CLASS_SUFFIX],
        }
        assert resolve_enabled_rules(config) == {RS_ACRONYM_CASING}

    def test_UnknownRuleIdInSelect_Raises(self) -> None:
        with pytest.raises(ValueError, match="RS999"):
            resolve_enabled_rules({"select": [RS_ACRONYM_CASING, "RS999"]})

    def test_UnknownRuleIdInIgnore_Raises(self) -> None:
        with pytest.raises(ValueError, match="RS999"):
            resolve_enabled_rules({"ignore": ["RS999"]})

    def test_AllUnknownSelect_RaisesRatherThanRunningNothing(self) -> None:
        with pytest.raises(ValueError):
            resolve_enabled_rules({"select": ["RS999"]})


class TestLintPathWithEnabledRules:
    def test_SelectSubset_RunsOnlyThoseRules(self, tmp_path: Path) -> None:
        target = tmp_path / "x.py"
        target.write_text(_ACRONYM_AND_SUFFIX_SOURCE, encoding="utf-8")
        rules = {v.rule for v in lint_path(target, {RS_ACRONYM_CASING})}
        assert rules == {RS_ACRONYM_CASING}

    def test_DefaultAllRules_FlagsBothViolations(self, tmp_path: Path) -> None:
        target = tmp_path / "x.py"
        target.write_text(_ACRONYM_AND_SUFFIX_SOURCE, encoding="utf-8")
        rules = {v.rule for v in lint_path(target, set(ALL_RULE_IDS))}
        assert RS_ACRONYM_CASING in rules
        assert RS_DISCOURAGED_CLASS_SUFFIX in rules

    def test_IgnoreRemovesRule_OnlyOtherFlagged(self, tmp_path: Path) -> None:
        target = tmp_path / "x.py"
        target.write_text(_ACRONYM_AND_SUFFIX_SOURCE, encoding="utf-8")
        enabled = resolve_enabled_rules({"ignore": [RS_DISCOURAGED_CLASS_SUFFIX]})
        rules = {v.rule for v in lint_path(target, enabled)}
        assert RS_DISCOURAGED_CLASS_SUFFIX not in rules
        assert RS_ACRONYM_CASING in rules

    def test_SuppressionComment_DropsThatFinding(self, tmp_path: Path) -> None:
        target = tmp_path / "x.py"
        target.write_text(
            "class FhirManager: ...  # style: ignore[RS001]\n", encoding="utf-8"
        )
        rules = {v.rule for v in lint_path(target, {RS_ACRONYM_CASING})}
        assert rules == set()

    def test_MarkdownDirectiveLookalike_DoesNotSuppress(self, tmp_path: Path) -> None:
        target = tmp_path / "doc.md"
        target.write_text("# style: ignore and ``X`` here\n", encoding="utf-8")
        rules = {v.rule for v in lint_path(target, {RS_NO_DOUBLE_BACKTICKS})}
        assert rules == {RS_NO_DOUBLE_BACKTICKS}

    def test_RS005_CoversMarkdownAndDocstrings(self, tmp_path: Path) -> None:
        markdown = tmp_path / "doc.md"
        markdown.write_text("See ``X`` here.\n", encoding="utf-8")
        python = tmp_path / "m.py"
        python.write_text('"""See ``X`` here."""\n', encoding="utf-8")
        enabled = {RS_NO_DOUBLE_BACKTICKS}
        assert [v.rule for v in lint_path(markdown, enabled)] == [
            RS_NO_DOUBLE_BACKTICKS
        ]
        assert [v.rule for v in lint_path(python, enabled)] == [RS_NO_DOUBLE_BACKTICKS]


class TestLoadConfig:
    def test_ReadsRepostyleTable_FromPyproject(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[tool.repostyle]\nselect = ["RS001"]\nignore = ["RS011"]\n',
            encoding="utf-8",
        )
        config = load_config(pyproject)
        assert config == {"select": ["RS001"], "ignore": ["RS011"]}

    def test_MissingTable_ReturnsNone(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[tool.other]\nfoo = "bar"\n', encoding="utf-8")
        assert load_config(pyproject) is None


class TestResolveEnabledRulesForPaths:
    def test_NearestPyprojectResolvesSelection_WalkingUp(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[tool.repostyle]\nselect = ["RS001"]\n', encoding="utf-8")
        nested = tmp_path / "src" / "pkg"
        nested.mkdir(parents=True)
        target = nested / "x.py"
        target.write_text("x = 1\n", encoding="utf-8")
        assert resolve_enabled_rules_for_paths([target]) == {RS_ACRONYM_CASING}

    def test_NoPyprojectInTree_DefaultsToAllRules(self, tmp_path: Path) -> None:
        target = tmp_path / "lonely.py"
        target.write_text("x = 1\n", encoding="utf-8")
        if find_pyproject(target) is not None:
            pytest.skip("temp tree has an ancestor pyproject.toml")
        assert resolve_enabled_rules_for_paths([target]) == set(ALL_RULE_IDS)


class TestLintPaths:
    def test_AggregatesAcrossPaths(self, tmp_path: Path) -> None:
        first = tmp_path / "a.py"
        first.write_text("class FhirClient: ...\n", encoding="utf-8")
        second = tmp_path / "b.py"
        second.write_text("class StringUtils: ...\n", encoding="utf-8")
        rules = {v.rule for v in lint_paths([first, second], set(ALL_RULE_IDS))}
        assert RS_ACRONYM_CASING in rules
        assert RS_DISCOURAGED_CLASS_SUFFIX in rules


class TestExpandPaths:
    def test_Directory_ExpandsToLintableFilesSorted(self, tmp_path: Path) -> None:
        (tmp_path / "b.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
        (tmp_path / "notes.txt").write_text("x\n", encoding="utf-8")
        assert expand_paths([tmp_path]) == [tmp_path / "a.py", tmp_path / "b.py"]

    def test_Directory_RecursesIntoSubdirectories(self, tmp_path: Path) -> None:
        nested = tmp_path / "pkg"
        nested.mkdir()
        target = nested / "x.py"
        target.write_text("x = 1\n", encoding="utf-8")
        assert expand_paths([tmp_path]) == [target]

    def test_Directory_SkipsDotAndBuildDirectories(self, tmp_path: Path) -> None:
        for skipped in (".git", "build", "__pycache__"):
            hidden = tmp_path / skipped
            hidden.mkdir()
            (hidden / "x.py").write_text("x = 1\n", encoding="utf-8")
        assert expand_paths([tmp_path]) == []

    def test_File_PassesThroughRegardlessOfSuffix(self, tmp_path: Path) -> None:
        target = tmp_path / "notes.txt"
        target.write_text("x\n", encoding="utf-8")
        assert expand_paths([target]) == [target]

    @pytest.mark.parametrize(
        "second_arg", ["file", "nested_dir"], ids=["file", "nested_dir"]
    )
    def test_OverlappingArgument_DropsTheDuplicate(
        self, tmp_path: Path, second_arg: str
    ) -> None:
        nested = tmp_path / "pkg"
        nested.mkdir()
        target = nested / "x.py"
        target.write_text("x = 1\n", encoding="utf-8")
        second = target if second_arg == "file" else nested
        assert expand_paths([tmp_path, second]) == [target]

    @pytest.mark.parametrize(
        ("globs", "dropped", "kept"),
        [
            ('["*_grpc/*.py"]', ["pkg/_grpc/stub.py"], ["pkg/app.py"]),
            (
                '["vendor/*", "*_pb2.py"]',
                ["vendor/lib.py", "service_pb2.py"],
                ["app.py"],
            ),
        ],
        ids=["single_glob", "multiple_globs"],
    )
    def test_ExcludeGlobs_DropsMatchingFiles(
        self, tmp_path: Path, globs: str, dropped: list[str], kept: list[str]
    ) -> None:
        _write_exclude_config(tmp_path, globs)
        for relative in [*dropped, *kept]:
            target = tmp_path / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("x = 1\n", encoding="utf-8")
        expanded = expand_paths([tmp_path])
        assert {tmp_path / relative for relative in dropped}.isdisjoint(expanded)
        assert {tmp_path / relative for relative in kept} <= set(expanded)

    def test_ExcludedFilePassedExplicitly_DropsFromScan(self, tmp_path: Path) -> None:
        _write_exclude_config(tmp_path, '["_grpc/*.py"]')
        generated = tmp_path / "_grpc"
        generated.mkdir()
        stub = generated / "stub.py"
        stub.write_text("x = 1\n", encoding="utf-8")
        assert expand_paths([stub]) == []

    def test_NoExcludeConfigured_ScansEverything(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.repostyle]\n", encoding="utf-8")
        first = tmp_path / "a.py"
        first.write_text("x = 1\n", encoding="utf-8")
        second = tmp_path / "b.py"
        second.write_text("x = 1\n", encoding="utf-8")
        expanded = expand_paths([tmp_path])
        assert first in expanded
        assert second in expanded


class TestLintPackage:
    def test_RootPathsOverride_ScansTheOriginalArgumentsTree(
        self, tmp_path: Path
    ) -> None:
        """Without `root_paths`, the scan misses the call to `helper` in
        `outer.py` and misreports it as should-be-private; passing `root_paths`
        widens the scan to the real package root and the finding disappears.
        """
        nested = tmp_path / "aaa_sub"
        nested.mkdir()
        target = nested / "mod.py"
        target.write_text(
            '__all__ = ["run"]\n\n\ndef helper():\n    return 1\n\n\n'
            "def run():\n    return helper()\n",
            encoding="utf-8",
        )
        (tmp_path / "outer.py").write_text(
            "def go():\n    return helper()\n", encoding="utf-8"
        )
        expanded = [target]
        narrow = lint_package(expanded, {RS_SHOULD_BE_PRIVATE})
        broad = lint_package(expanded, {RS_SHOULD_BE_PRIVATE}, root_paths=[tmp_path])
        assert target.resolve() in narrow
        assert broad == {}


class TestFixPath:
    def test_UnderwrappedDocstring_RewritesFileAndReportsChange(
        self, tmp_path: Path
    ) -> None:
        target = tmp_path / "x.py"
        target.write_text(_UNDERWRAPPED_DOCSTRING, encoding="utf-8")
        assert fix_path(target, {RS_DOC_FILL}) is True
        assert "    aaa bbb\n" in target.read_text(encoding="utf-8")

    @pytest.mark.parametrize(
        ("filename", "source", "enabled"),
        [
            (
                "x.py",
                'def f():\n    """Summary.\n\n    aaa bbb\n    """\n',
                {RS_DOC_FILL},
            ),
            ("x.py", _UNDERWRAPPED_DOCSTRING, {RS_ACRONYM_CASING}),
            ("doc.md", "aaa\nbbb\n", {RS_DOC_FILL}),
            ("x.py", "# style: ignore-file\n" + _UNDERWRAPPED_DOCSTRING, {RS_DOC_FILL}),
        ],
        ids=["already_filled", "rule_off", "non_python", "file_suppressed"],
    )
    def test_NoFixableFinding_LeavesFileAndReportsFalse(
        self, tmp_path: Path, filename: str, source: str, enabled: set[str]
    ) -> None:
        target = tmp_path / filename
        target.write_text(source, encoding="utf-8")
        assert fix_path(target, enabled) is False
        assert target.read_text(encoding="utf-8") == source

    def test_LineSuppressed_LeavesUnitUntouched(self, tmp_path: Path) -> None:
        source = "# aaa\n# bbb  # style: ignore[RS009]\nx = 1\n"
        target = tmp_path / "x.py"
        target.write_text(source, encoding="utf-8")
        assert fix_path(target, {RS_DOC_FILL}) is False
        assert target.read_text(encoding="utf-8") == source


class TestSeverityOf:
    @pytest.mark.parametrize(
        "rule_id", [RS_ACRONYM_CASING, "RS999"], ids=["known_rule", "unknown_id"]
    )
    def test_NoSeverityOverride_DefaultsToError(self, rule_id: str) -> None:
        assert severity_of(rule_id) is Severity.ERROR


@pytest.mark.parametrize("rule_id", sorted(ALL_RULE_IDS))
def test_EveryRuleIdRunnable_NoCrash(rule_id: str, tmp_path: Path) -> None:
    target = tmp_path / "probe.py"
    target.write_text("x = 1\n", encoding="utf-8")
    assert isinstance(lint_path(target, {rule_id}), list)


def _write_exclude_config(tmp_path: Path, exclude: str) -> None:
    (tmp_path / "pyproject.toml").write_text(
        f"[tool.repostyle]\nexclude = {exclude}\n", encoding="utf-8"
    )
