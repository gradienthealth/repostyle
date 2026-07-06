# repostyle

A stdlib-only AST/token/line linter for repo-style conventions that ruff cannot express, shared across gradienthealth repos and run as a pre-commit remote hook. It is the extraction of fhir-ingestor's `scripts/check_repo_style.py` into a versioned package, so the `RSnnn` rules here are the canonical source the other repos consume. Most rules are Python-specific (AST-based); the comment-convention rules RS009 (paragraph wrapping) and RS030 (terminal punctuation) also run over TOML and YAML comments through a shared `#`-comment extractor, so a `#` comment is held to the same prose conventions whatever the language.

## Project context

Consuming repos add the hook to their `.pre-commit-config.yaml` pinned to a `repostyle-vX.Y.Z` tag, select the rule subset they want through a `[tool.repostyle]` table in their `pyproject.toml`, and inherit the base ruff settings from `ruff-base.toml`. Two rules are tied to fhir-ingestor's hexagonal layout (RS002 test naming, RS006 port purity) and RS003 (mock ban) presumes a `tests/fakes/` directory; a repo without those conventions should not select them. The rest are general.

The `RSnnn` rules are the *subject matter* this package enforces on other repos. Their definitions, scope, and rationale live in the rule docstrings in the themed modules under `src/repostyle/rules/`; read the relevant module before changing rule behavior.

## Repository layout

- `src/repostyle/rules/` — the rules package. Themed modules hold the `check_*` functions (`naming` — acronym casing, abbreviations, class suffixes, the boolean-naming rules RS024 (no embedded negation) and RS026 (a `bool`-annotated name needs an `is`/`has`/`can`/`should` prefix, both warning severity), and the make-in-production rule RS025 — `docstrings` — the docstring and markdown prose rules RS004/RS005 plus the documentation-form rules RS020 (leading summary comment should be a docstring), RS021 (dataclass field comment should be a field docstring), RS023 (no filler docstring opening), and RS034 (docstring summary opens descriptively, not imperatively, against a fixed verb list; warning severity), plus the docstring half of RS030 (terminal punctuation: every docstring prose unit — the summary, a body paragraph, and an `Args:`/`Returns:`/`Raises:`/`Yields:` entry — ends with `.`/`!`/`?`, per PEP 257; warning severity) — `doc_fill`, `testing` — test naming, the mock ban, and the test-quality rules RS013–RS016 — `complexity`, `doc_value` — the RS018 documentation-value signal, RS031 (per-argument detail narrated in docstring prose belongs in an `Args:` section, warning severity), and RS032 (return-value detail narrated in docstring prose belongs in a `Returns:` section, warning severity) — `import_layering` — the config-driven RS017 banned-import-by-path rule — `layout` — the structural RS019 element-ordering rule (top-down module order plus alphabetical for free choices, and class member order, warning severity) — `comments` — the config-driven RS022 comment-tag format rule and the comment half of RS030 (terminal punctuation), both run over Python, TOML, and YAML comments — `signatures` — the RS027 too-many-positional-arguments rule, a stand-in for ruff's preview-gated PLR0917 (delete it for PLR0917 when that graduates; PROC-2319) — `ports`, `duration`, `logging_phi`, `filenames` — the config-driven RS033 filename-convention rule (preferred extension and casing) applied to a file's name on disk rather than its content, `.py` files exempt); `_violation` holds the `Violation` record, the `Severity` enum, and the `RSnnn` id constants; `_comments` holds `extract_comments`, the per-language `#`-comment extractor that RS009, RS022, RS030, and the suppression parser share (Python via the tokenizer, TOML and YAML via a string- and block-aware line scan), plus `COMMENT_SUFFIXES`; `_shared` holds helpers used by more than one module (including `find_pyproject`); `_registry` holds the `RULES` mapping (id to a tuple of check functions), `run_rule`, and `ALL_RULE_IDS`; `_catalog` holds the agent-facing rule metadata (`RuleDoc`/`GoodBad`, the `RULE_DOCS` mapping, `rule_doc`, `has_guidance`) the `explain` surface renders from — every rule carries a one-line `summary`, the rules where general knowledge falls short carry richer `rationale`/`examples`/`signals`/`reference`. The package `__init__` re-exports the whole public surface, so `from repostyle.rules import <name>` is stable. Add a rule by writing a `check_*` function in the module it belongs to, registering it in `_registry.RULES`, re-exporting it from `__init__`, adding a `RuleDoc` to `_catalog.RULE_DOCS`, and adding a parametrized test.
- `src/repostyle/runner.py` — config resolution (`select` minus `ignore`), pyproject discovery, and linting a path with the enabled rule set.
- `src/repostyle/suppressions.py` — the `# style: ignore[RSnnn]` line and `# style: ignore-file` whole-file directives the runner applies to drop findings.
- `src/repostyle/changed_lines.py` — the git-diff line set the CLI's `--diff` mode intersects findings against, so a finding is reported only on lines the change touched.
- `src/repostyle/cli.py` — the `repostyle` console script the hook invokes; a directory argument recurses into its lintable files (pre-commit itself always passes individual files), its `--diff` flag scopes findings to git-changed lines, its `--fix` flag rewrites the mechanically-fixable findings in place (RS005 double-to-single backticks, RS009 reflow, RS030 terminal punctuation — the set in `_registry.FIXABLE_RULES`), and its `explain RSnnn`/`explain --all` subcommand prints a rule's card. A finding from a rule with a card prints a one-line `explain` pointer to stderr unless `--no-explain-hint` is passed.
- `src/repostyle/explain.py` — renders a `RuleDoc` into the agent-facing explanation card (`explain_rule`) and the discovery hint, wrapping prose to 79 columns and leaving example code verbatim.
- `tests/` — `test_rules.py` (per-rule behavior), `test_runner.py` (config and dispatch), `test_cli.py` (CLI output and exit status), `test_suppressions.py` (suppression directives), `test_changed_lines.py` (the `--diff` line set), `test_complexity.py` (RS012), `test_import_layering.py` (RS017), `test_doc_value.py` (RS018, RS031, RS032), `test_layout.py` (RS019), `test_doc_form.py` (RS020, RS021, RS023, RS034), `test_comment_tags.py` (RS022), `test_signatures.py` (RS027), `test_filenames.py` (RS033), `test_cross_language.py` (the `extract_comments` `#`-comment extractor for TOML and YAML, plus the cross-language behaviour of RS009/RS030), `test_explain.py` (the `explain` cards, the catalog-completeness and abbreviation-map checks, and `has_guidance`), and `test_fix.py` (the RS005/RS030 fixers and the `--fix` composition in `runner.fix_path`), with a git repo from the `conftest.py` fixture.
- `ruff-base.toml`, `.pre-commit-hooks.yaml` — the shared ruff baseline and the hook definitions consumers reference. `.pre-commit-hooks.yaml` exports both the `repostyle` linter hook and the `repostyle-*` gate hooks (bandit, vulture, deptry, interrogate, codespell) that wrap the house third-party gates with their versions pinned here; mypy, pyright, and pip-audit stay consumer-side because they need the consuming repo's own environment.

## Style this repo holds itself to

These are the general conventions from fhir-ingestor's `docs/code-style.md` and `docs/testing.md` (the deeper rationale lives there) — the subset that applies to this package's own code. Several are rules this package itself defines, so it holds itself to them too.

- Descriptive Google-style docstrings stating the unit's own contract in the third person (`Returns the lease.`, not `Return the lease.`; RS034 catches the common openings) — no caller postulation, no implementation mechanics, no narration of rejected alternatives. Comments only where the *why* is non-obvious.
- Line length 88; docstring and comment paragraphs fill to 79 columns (RS009).
- Single backticks in docstrings and prose, never double (RS005).
- Every docstring prose unit — the summary, a body paragraph, and an `Args:`/`Returns:`/`Raises:`/`Yields:` entry — ends with terminal punctuation (`.`, `!`, or `?`), per PEP 257 (RS030, warning). A comment, by contrast, takes no trailing period on a single-line fragment but punctuates multi-line or multi-sentence prose.
- Acronyms stay uppercase in CapWords identifiers (RS001): `FHIRClient`, not `FhirClient`.
- Spell names out; the banned abbreviations in RS010 (`cfg`, `ctx`, `req`, `resp`, `conn`, ...) are rejected. Name a class for its responsibility, not a vague `Manager`/`Helper`/`Util` role (RS011). Booleans read as a positive yes/no question: a `bool`-annotated name carries an `is`/`has`/`can`/`should` prefix (RS026) and never embeds `not` or `no` (RS024); both warn rather than fail. `make_` is for test fixtures only; a production `make_` is rejected (RS025). An `except ... as` alias is `exc` (`exc2` when nested) or a descriptive name, never `e`/`ex`/`err` (RS028).
- Per-field attribute docstrings on dataclasses, not a Google `Attributes:` block (RS004). Module-level duration constants are `timedelta`, not raw `*_SECONDS` numbers (RS007).
- A non-Python filename prefers `.yaml` over `.yml` and kebab-case for a multi-word name, except `CLAUDE.md` (a fixed name Claude Code's tooling looks up exactly) and `README.md`/`CHANGELOG.md` (the older, more entrenched Unix/GNU and GitHub community-health-file convention of all-caps project metadata) (RS033, warning).
- No relative imports; strict type hints.

Testing:

- Test functions follow `test_<StateUnderTest>_<ExpectedBehavior>` in PascalCase (RS002), one test class per public callable, ordered happy path then edge then error.
- Fakes, not mocks; assert observable outcomes, not call choreography; collapse cosmetic input variation into `@pytest.mark.parametrize` with `ids`.

## Commits and PRs

The repo squash-merges, so the PR title becomes the commit subject on `main`, and release-please reads that subject to compute the version bump. Title PRs as Conventional Commits with the Linear ticket (or `NO-ISSUE`) in the scope:

- `feat(PROC-123): add the no-bare-except rule` — a feature, bumps the minor.
- `fix(NO-ISSUE): correct the doc-fill boundary off-by-one` — a fix, bumps the patch.
- `feat(PROC-123)!: ...` or a `BREAKING CHANGE:` footer — bumps the major (the minor while the package is pre-1.0).
- `chore`, `docs`, `ci`, `refactor`, `test` produce a changelog entry but no release.

The scope carries the ticket so the title satisfies both the conventional-commit check and the org-wide PR Title Check. The subject after the type is lowercase. Commit subjects (within a branch) stay imperative and need no ticket — the title carries it.

## Release

release-please maintains a release PR off `main`; merging it cuts the `repostyle-vX.Y.Z` tag, the GitHub Release, and the `CHANGELOG.md` entry, then the workflow builds the wheel and publishes it to the internal Artifact Registry at `us-central1-python.pkg.dev/gradient-health-resources/python-packages`. The version in `pyproject.toml` is release-please-managed; never edit it by hand. Consumers pin the `repostyle-v` tag in their pre-commit config, or `pip install` from the registry index for non-hook use.

## Where to find context

- The fuller style and testing rationale lives in `../fhir-ingestor/docs/` (`code-style.md`, `testing.md`), the origin of these conventions.
- Sibling gradienthealth repos are checked out under `../`.
- Resolve the Linear ticket in the PR title before reading a diff; do not invent motivation when the ticket or MCP tools are unreachable.

## Agentic conventions

CI is the floor that blocks merge: ruff format and lint, pytest on the 3.11 floor and 3.13 ceiling, the conventional-commit and org PR Title checks. Style beyond what those enforce is upheld by review. Take a branch from working tree to a finished PR with `/gradient-workflow:submit-pr`; never amend or force-push a shared branch.
