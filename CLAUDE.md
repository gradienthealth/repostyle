# gradient-pystyle

A stdlib-only AST/token/line linter for repo-style conventions that ruff cannot express, shared across gradienthealth Python repos and run as a pre-commit remote hook. It is the extraction of fhir-ingestor's `scripts/check_repo_style.py` into a versioned package, so the `RSnnn` rules here are the canonical source the other repos consume.

## Project context

Consuming repos add the hook to their `.pre-commit-config.yaml` pinned to a `gradient-pystyle-vX.Y.Z` tag, select the rule subset they want through a `[tool.gradient-pystyle]` table in their `pyproject.toml`, and inherit the base ruff settings from `ruff-base.toml`. Two rules are tied to fhir-ingestor's hexagonal layout (RS002 test naming, RS006 port purity) and RS003 (mock ban) presumes a `tests/fakes/` directory; a repo without those conventions should not select them. The rest are general.

The `RSnnn` rules are the *subject matter* this package enforces on other repos. Their definitions, scope, and rationale live in the rule docstrings in the themed modules under `src/gradient_pystyle/rules/`; read the relevant module before changing rule behavior.

## Repository layout

- `src/gradient_pystyle/rules/` — the rules package. Themed modules hold the `check_*` functions (`naming`, `docstrings`, `doc_fill`, `testing` — test naming, the mock ban, and the test-quality rules RS013–RS016 — `complexity`, `import_layering` — the config-driven RS017 banned-import-by-path rule — `ports`, `duration`, `logging_phi`); `_violation` holds the `Violation` record, the `Severity` enum, and the `RSnnn` id constants; `_shared` holds helpers used by more than one module (including `find_pyproject`); `_registry` holds the `RULES` mapping (id to a tuple of check functions), `run_rule`, and `ALL_RULE_IDS`. The package `__init__` re-exports the whole public surface, so `from gradient_pystyle.rules import <name>` is stable. Add a rule by writing a `check_*` function in the module it belongs to, registering it in `_registry.RULES`, re-exporting it from `__init__`, and adding a parametrized test.
- `src/gradient_pystyle/runner.py` — config resolution (`select` minus `ignore`), pyproject discovery, and linting a path with the enabled rule set.
- `src/gradient_pystyle/suppressions.py` — the `# style: ignore[RSnnn]` line and `# style: ignore-file` whole-file directives the runner applies to drop findings.
- `src/gradient_pystyle/changed_lines.py` — the git-diff line set the CLI's `--diff` mode intersects findings against, so a finding is reported only on lines the change touched.
- `src/gradient_pystyle/cli.py` — the `gradient-pystyle` console script the hook invokes; its `--diff` flag scopes findings to git-changed lines and its `--fix` flag rewraps RS009 findings in place.
- `tests/` — `test_rules.py` (per-rule behavior), `test_runner.py` (config and dispatch), `test_cli.py` (CLI output and exit status), `test_suppressions.py` (suppression directives), `test_changed_lines.py` (the `--diff` line set), `test_complexity.py` (RS012), and `test_import_layering.py` (RS017), with a git repo from the `conftest.py` fixture.
- `ruff-base.toml`, `.pre-commit-hooks.yaml` — the shared ruff baseline and the hook definition consumers reference.

## Style this repo holds itself to

These are the general conventions from fhir-ingestor's `docs/code-style.md` and `docs/testing.md` (the deeper rationale lives there) — the subset that applies to this package's own code. Several are rules this package itself defines, so it holds itself to them too.

- Imperative Google-style docstrings stating the unit's own contract — no caller postulation, no implementation mechanics, no narration of rejected alternatives. Comments only where the *why* is non-obvious.
- Line length 88; docstring and comment paragraphs fill to 72 columns (RS009).
- Single backticks in docstrings and prose, never double (RS005).
- Acronyms stay uppercase in CapWords identifiers (RS001): `FHIRClient`, not `FhirClient`.
- Spell names out; the banned abbreviations in RS010 (`cfg`, `ctx`, `req`, `resp`, `conn`, ...) are rejected. Name a class for its responsibility, not a vague `Manager`/`Helper`/`Util` role (RS011).
- Per-field attribute docstrings on dataclasses, not a Google `Attributes:` block (RS004). Module-level duration constants are `timedelta`, not raw `*_SECONDS` numbers (RS007).
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

release-please maintains a release PR off `main`; merging it cuts the `gradient-pystyle-vX.Y.Z` tag, the GitHub Release, and the `CHANGELOG.md` entry, then the workflow builds the wheel and publishes it to the internal Artifact Registry at `us-central1-python.pkg.dev/gradient-health-resources/python-packages`. The version in `pyproject.toml` is release-please-managed; never edit it by hand. Consumers pin the `gradient-pystyle-v` tag in their pre-commit config, or `pip install` from the registry index for non-hook use.

## Where to find context

- The fuller style and testing rationale lives in `../fhir-ingestor/docs/` (`code-style.md`, `testing.md`), the origin of these conventions.
- Sibling gradienthealth repos are checked out under `../`.
- Resolve the Linear ticket in the PR title before reading a diff; do not invent motivation when the ticket or MCP tools are unreachable.

## Agentic conventions

CI is the floor that blocks merge: ruff format and lint, pytest on the 3.11 floor and 3.13 ceiling, the conventional-commit and org PR Title checks. Style beyond what those enforce is upheld by review. Take a branch from working tree to a finished PR with `/gradient-workflow:submit-pr`; never amend or force-push a shared branch.
