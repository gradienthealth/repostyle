"""Resolves the enabled-rule set from config and lints paths with it."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import NamedTuple

from repostyle._discovery import (
    LINTABLE_SUFFIXES,
    _package_files,
)
from repostyle._discovery import (
    expand_paths as _expand_paths,
)
from repostyle._shared import (
    _repostyle_table,
    config_table,
    find_config_file,
)
from repostyle.baseline import DEFAULT_BASELINE_NAME
from repostyle.languages import LANGUAGES
from repostyle.rules import (
    ALL_RULE_IDS,
    FIXABLE_RULES,
    PACKAGE_RULES,
    RS_ACRONYM_CASING_IN_PROSE,
    RS_DISFAVORED_GCP_TERM,
    RS_DOC_FILL,
    RS_DOCSTRING_SECTION_ALIAS,
    RS_DOUBLE_SPACE_AFTER_PERIOD,
    RS_NO_DOUBLE_BACKTICKS,
    RS_NONSTANDARD_DASH,
    RS_TERMINAL_PUNCTUATION,
    Violation,
    fix_acronym_casing_in_comments,
    fix_acronym_casing_in_docstrings,
    fix_comment_terminal_punctuation,
    fix_disfavored_gcp_term_in_comments,
    fix_disfavored_gcp_term_in_docstrings,
    fix_doc_fill,
    fix_docstring_section_alias,
    fix_docstring_terminal_punctuation,
    fix_double_backticks,
    fix_double_space_in_comments,
    fix_double_space_in_docstrings,
    fix_nonstandard_dash_in_comments,
    fix_nonstandard_dash_in_docstrings,
    run_package_rule,
    run_rule,
)
from repostyle.suppressions import filter_suppressed, suppressed_lines

# Each fixer rewrites one rule's findings, taking `(path, source,
# skip_lines)` and returning the rewritten source. They run in this
# order so the surface edits (backticks, dashes, terminal punctuation)
# settle before the reflow rewraps the corrected prose -- a dash rewrite
# changes line length, so the reflow must run after it; each re-parses
# the source it is handed, so chaining their edits is safe.
_Fixer = Callable[[Path, str, frozenset[int]], str]
_FIXERS: tuple[tuple[str, _Fixer], ...] = (
    (RS_NO_DOUBLE_BACKTICKS, fix_double_backticks),
    (RS_DOCSTRING_SECTION_ALIAS, fix_docstring_section_alias),
    (RS_ACRONYM_CASING_IN_PROSE, fix_acronym_casing_in_docstrings),
    (RS_ACRONYM_CASING_IN_PROSE, fix_acronym_casing_in_comments),
    (RS_DISFAVORED_GCP_TERM, fix_disfavored_gcp_term_in_docstrings),
    (RS_DISFAVORED_GCP_TERM, fix_disfavored_gcp_term_in_comments),
    (RS_NONSTANDARD_DASH, fix_nonstandard_dash_in_docstrings),
    (RS_NONSTANDARD_DASH, fix_nonstandard_dash_in_comments),
    (RS_TERMINAL_PUNCTUATION, fix_docstring_terminal_punctuation),
    (RS_TERMINAL_PUNCTUATION, fix_comment_terminal_punctuation),
    (RS_DOUBLE_SPACE_AFTER_PERIOD, fix_double_space_in_docstrings),
    (RS_DOUBLE_SPACE_AFTER_PERIOD, fix_double_space_in_comments),
    (RS_DOC_FILL, fix_doc_fill),
)


class _ResolvedRules(NamedTuple):
    """Pairs the runnable rule ids with advisory ids elevated to errors."""

    enabled: set[str]
    promoted: set[str]


def expand_paths(paths: Iterable[Path]) -> list[Path]:
    """Replaces directory arguments with the lintable files beneath them."""
    return _expand_paths(paths)


def resolve_enabled_rules_for_paths(paths: Iterable[Path]) -> set[str]:
    """Discovers config from the first path's directory and resolves rules."""
    return resolve_rules_for_paths(paths).enabled


def resolve_rules_for_paths(paths: Iterable[Path]) -> _ResolvedRules:
    """Discovers config from the first path's directory and resolves rules.

    Loads the `[tool.repostyle]` table once and derives both the enabled set
    and the error-promotion set from it, so the config is read a single time.

    Raises:
        ValueError: When the table names an unknown rule id or sets `baseline`
            to anything but a nonempty path string or `false`.
    """
    paths = list(paths)
    if not paths:
        return _ResolvedRules(set(ALL_RULE_IDS), set())
    pyproject = find_config_file(paths[0])
    config = load_config(pyproject) if pyproject is not None else None
    _check_baseline_setting(config)
    _check_languages_setting(config)
    return _ResolvedRules(resolve_enabled_rules(config), resolve_promoted_rules(config))


def baseline_opted_out(paths: Iterable[Path]) -> bool:
    """Reports whether the repo holding `paths` sets `baseline = false`.

    An opted-out repo keeps no baseline: every finding counts against it, and
    writing or refreshing a baseline file is refused.
    """
    paths = list(paths)
    if not paths:
        return False
    return _repostyle_table(find_config_file(paths[0])).get("baseline") is False


def resolve_baseline_path(paths: Iterable[Path]) -> Path | None:
    """Returns the baseline file the repo holding `paths` uses, if any.

    The path is `[tool.repostyle] baseline` resolved against the directory of
    the `pyproject.toml` that declares it, so a run from any directory reads
    one file. An unset key falls back to `DEFAULT_BASELINE_NAME` beside the
    `pyproject.toml`, which is only consulted when it exists, so a repo that
    has not adopted a baseline needs no config.

    Returns:
        The baseline file's path, or `None` when there is no `pyproject.toml`,
        no configured or default file, or the repo sets `baseline = false`,
        which opts out even when the default file exists.
    """
    paths = list(paths)
    if not paths:
        return None
    pyproject = find_config_file(paths[0])
    if pyproject is None:
        return None
    configured = _repostyle_table(pyproject).get("baseline")
    if configured is False:
        return None
    if isinstance(configured, str) and configured:
        return pyproject.parent / configured
    default = pyproject.parent / DEFAULT_BASELINE_NAME
    return default if default.is_file() else None


def repo_root(paths: Iterable[Path]) -> Path:
    """Returns the directory baseline keys are relative to.

    The `pyproject.toml` directory is the root, falling back to the first
    path's own directory outside a project, so a key is stable wherever the run
    is invoked from.
    """
    paths = list(paths)
    if not paths:
        return Path.cwd()
    pyproject = find_config_file(paths[0])
    if pyproject is not None:
        return pyproject.parent
    first = paths[0].resolve()
    return first if first.is_dir() else first.parent


def load_config(pyproject: Path) -> dict | None:
    """Returns the repostyle settings in a config file, or `None` for none."""
    return config_table(pyproject)


def _check_baseline_setting(config: dict | None) -> None:
    """Rejects a `baseline` value that is neither a path nor `false`.

    `baseline = true` reads like an opt-in but names no file, so it is refused
    rather than treated as unset.

    Raises:
        ValueError: When `baseline` is set to anything but a nonempty string or
            `false`.
    """
    if not config or "baseline" not in config:
        return
    configured = config["baseline"]
    if configured is False or (isinstance(configured, str) and configured):
        return
    raise ValueError(
        f"invalid `baseline` value {configured!r}: set a path to the baseline "
        "file, or `false` to opt out of a baseline"
    )


def _check_languages_setting(config: dict | None) -> None:
    """Rejects a `languages` value that is not a list of known language names.

    An unknown name is refused rather than ignored, since a misspelled `"jav"`
    would otherwise leave Java unlinted without a word.

    Raises:
        ValueError: When `languages` is not a list of strings or names a
            language repostyle does not read.
    """
    if not config or "languages" not in config:
        return
    configured = config["languages"]
    known = {language.name for language in LANGUAGES}
    if not isinstance(configured, list) or not all(
        isinstance(name, str) for name in configured
    ):
        raise ValueError(
            f"invalid `languages` value {configured!r}: list language names "
            f"from {', '.join(sorted(known))}"
        )
    unknown = set(configured) - known
    if unknown:
        raise ValueError(
            f"unknown repostyle language(s): {', '.join(sorted(unknown))}. "
            f"Known languages: {', '.join(sorted(known))}."
        )


def resolve_enabled_rules(config: dict | None) -> set[str]:
    """Resolves enabled rule ids from a `[tool.repostyle]` table.

    `select` defaults to every rule; `ignore` defaults to none. The enabled set
    is `select` minus `ignore`. A missing or empty table enables all rules.

    Raises:
        ValueError: When `select` or `ignore` names an unknown id. Silently
            dropping it could resolve `select` to the empty set and make the
            linter pass everything.
    """
    if not config:
        return set(ALL_RULE_IDS)
    known = set(ALL_RULE_IDS)
    select = config.get("select")
    ignore = config.get("ignore", [])
    unknown = (set(select or ()) | set(ignore)) - known
    if unknown:
        raise ValueError(
            "unknown repostyle rule id(s): "
            f"{', '.join(sorted(unknown))}. Known ids: {', '.join(sorted(known))}."
        )
    selected = set(select) if select else known
    return selected - set(ignore)


def resolve_promoted_rules(config: dict | None) -> set[str]:
    """Resolves the ids promoted to error from a `[tool.repostyle]` table.

    Rules keep their catalog severity by default. The `error` list promotes
    individual advisory rules. `warnings-as-errors = true` promotes every rule.
    A disabled rule may be promoted, but that promotion remains inert.

    Raises:
        ValueError: When `error` names an unknown id, matching how
            `resolve_enabled_rules` validates `select` and `ignore`.
    """
    known = set(ALL_RULE_IDS)
    promoted = set(config.get("error", [])) if config else set()
    unknown = promoted - known
    if unknown:
        raise ValueError(
            "unknown repostyle rule id(s): "
            f"{', '.join(sorted(unknown))}. Known ids: {', '.join(sorted(known))}."
        )
    return known if config and config.get("warnings-as-errors") is True else promoted


def lint_paths(paths: Iterable[Path], enabled: set[str]) -> list[Violation]:
    return [v for path in paths for v in lint_path(path, enabled)]


def lint_path(path: Path, enabled: set[str]) -> list[Violation]:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    violations: list[Violation] = []
    for rule_id in enabled:
        violations.extend(run_rule(rule_id, path, source))
    violations = filter_suppressed(path, violations, source)
    return sorted(set(violations))


def lint_package(
    paths: Iterable[Path],
    enabled: set[str],
    *,
    root_paths: Iterable[Path] | None = None,
) -> dict[Path, list[Violation]]:
    """Runs the enabled whole-package rules, scoped to the given paths.

    A package rule sees every first-party file under the repo root so its
    cross-module view is whole, but findings are reported only on the paths
    passed in -- keeping it sound under pre-commit's per-file batching. Returns
    findings keyed by each path's resolved location.

    Args:
        paths: The files findings are reported on, the pre-commit batch.
        enabled: The resolved rule set; only its package rules run here.
        root_paths: Locates the package root, defaulting to `paths`. Pass the
            pre-expansion arguments when `paths` has already been expanded from
            a directory, so the root is discovered from what the caller pointed
            at rather than an arbitrary file the expansion happened to sort
            first.
    """
    paths = list(paths)
    package_rules = enabled & set(PACKAGE_RULES)
    if not package_rules or not paths:
        return {}
    root_paths = list(root_paths) if root_paths is not None else paths
    root = find_config_file(root_paths[0])
    files = _package_files(root.parent if root is not None else root_paths[0])
    sources = {path.resolve(): source for path, source in files}
    scope = {path.resolve() for path in paths}
    findings: dict[Path, list[Violation]] = {}
    for rule_id in package_rules:
        for path, violation in run_package_rule(rule_id, files):
            resolved = path.resolve()
            if resolved in scope:
                findings.setdefault(resolved, []).append(violation)
    kept = {
        path: sorted(set(filter_suppressed(path, violations, sources.get(path, ""))))
        for path, violations in findings.items()
    }
    return {path: violations for path, violations in kept.items() if violations}


def fix_path(path: Path, enabled: set[str]) -> bool:
    """Applies each enabled fixable rule to `path` in place, reporting change.

    A no-op unless a fixable rule is enabled and `path` is a Python, markdown,
    TOML, YAML, or shell file. The fixers run in `_FIXERS` order, each handed
    the output of the last; a comment fixer reaches every language the matching
    check reads, while a docstring fixer acts on Python alone. A whole-file
    ignore directive leaves the file untouched for that rule, and a per-line
    suppression leaves its line untouched.
    """
    if not enabled & FIXABLE_RULES or path.suffix not in LINTABLE_SUFFIXES:
        return False
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    original = source
    for rule_id, fixer in _FIXERS:
        if rule_id not in enabled:
            continue
        file_suppressed, skip = suppressed_lines(path, source, rule_id)
        if file_suppressed:
            continue
        source = fixer(path, source, skip)
    if source == original:
        return False
    path.write_text(source, encoding="utf-8")
    return True
