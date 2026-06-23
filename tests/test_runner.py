from pathlib import Path

import pytest

from gradient_pystyle.rules import (
    ALL_RULE_IDS,
    RS_ACRONYM_CASING,
    RS_DISCOURAGED_CLASS_SUFFIX,
    RS_NO_DOUBLE_BACKTICKS,
)
from gradient_pystyle.runner import (
    find_pyproject,
    lint_path,
    lint_paths,
    load_config,
    resolve_enabled_rules,
    resolve_enabled_rules_for_paths,
)

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


class TestConfigDiscovery:
    def test_ReadsGradientPystyleTable_FromPyproject(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[tool.gradient-pystyle]\nselect = ["RS001"]\nignore = ["RS011"]\n',
            encoding="utf-8",
        )
        config = load_config(pyproject)
        assert config == {"select": ["RS001"], "ignore": ["RS011"]}

    def test_MissingTable_ReturnsNone(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[tool.other]\nfoo = "bar"\n', encoding="utf-8")
        assert load_config(pyproject) is None

    def test_NearestPyprojectResolvesSelection_WalkingUp(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(
            '[tool.gradient-pystyle]\nselect = ["RS001"]\n', encoding="utf-8"
        )
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


@pytest.mark.parametrize("rule_id", sorted(ALL_RULE_IDS))
def test_EveryRuleIdRunnable_NoCrash(rule_id: str, tmp_path: Path) -> None:
    target = tmp_path / "probe.py"
    target.write_text("x = 1\n", encoding="utf-8")
    assert isinstance(lint_path(target, {rule_id}), list)
