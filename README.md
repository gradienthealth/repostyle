# gradient-pystyle

Shared repo-style lint rules for gradienthealth Python repos, plus a base ruff config. The rules are a stdlib-only AST/token/line linter that catches conventions ruff does not cover; consuming repos select the subset they want and run it as a pre-commit remote hook.

## Rules

Each rule is identified by an `RSnnn` id and can be selected or ignored per repo.

| Rule | Description |
| -- | -- |
| RS001 | Acronym casing: a known acronym in a CapWords identifier must stay uppercase (`FHIRClient`, not `FhirClient`). |
| RS002 | Test naming: tests under `tests/unit/` must match `test_StateUnderTest_ExpectedBehavior`. |
| RS003 | No mock/patch: `unittest.mock` and `mock` imports are rejected outside `tests/fakes/`. |
| RS004 | No `Attributes:` block: use per-field attribute docstrings, not a Google `Attributes:` section. |
| RS005 | No double backticks: markdown prose and Python docstrings must use single backticks. |
| RS006 | Port purity: files under `application/ports/` must not name a concrete implementation library (httpx, sqlalchemy, bigquery, psycopg, boto3). |
| RS007 | Duration as timedelta: a module-level `*_SECONDS` constant with a numeric literal should be a `timedelta`. |
| RS008 | No PHI-safe with exc_info: a log record carrying `exc_info` may not be marked `phi_safe`. |
| RS009 | Doc fill: docstring and comment paragraphs must fill to 72 columns. |
| RS010 | No banned abbreviation: an introduced name may not use a known abbreviation (`cfg`, `ctx`, `req`, `resp`, `conn`, ...). |
| RS011 | No discouraged class suffix: a class may not end in `Manager`, `Helper`, `Util`, or `Utils`. |
| RS012 | Cognitive complexity (warning): a function whose nesting-weighted complexity exceeds 15 is flagged for a second look. |
| RS013 | Conditional test logic: a test may not wrap an `assert` in an `if`/`for`/`while`/`try`; keep the asserted path straight-line. |
| RS014 | Sleepy test: a test may not call `time.sleep` or `asyncio.sleep`; wait on a condition or a fake clock. |
| RS015 | Excessive mocking (warning): a test building more than 3 mock objects is flagged as a density signal of where to look. |
| RS016 | Behavior-verification-only (warning): a test asserting only call choreography (`mock.assert_called*`) and no observable state. |
| RS017 | Banned import by path: a file may not import a source its layer forbids, per a config-driven path-glob-to-sources map (see below). |
| RS018 | Documentation-value signal (warning): a non-trivial public function (by cognitive complexity or parameter count) that lacks a docstring; a documented many-parameter function with no structured `Args:` section; or a function returning a multi-element `tuple` with no `Returns:` section to name the elements. |
| RS019 | Element order (warning): a module-level definition above a definition that uses it, or independent private helpers and classes left out of alphabetical order; within a class, methods out of dunder-then-public-then-private band, or an explicit-value enum out of alphabetical order. |
| RS020 | Summary comment as docstring (warning): a module, class, or function with no docstring whose first body position is a standalone prose comment should carry that summary as a docstring, where ruff D401's mood check can see it. |
| RS021 | Field comment as docstring (warning): a `@dataclass` field documented with a trailing prose comment and no following string-literal docstring should use the per-field docstring the house style prefers. |
| RS022 | Comment-tag format: a special comment must read `TAG(TICKET): message` with an allowed tag (`TODO`, `FIXME`, `NOTE`, `HACK`) and a ticket matching a configured pattern (see below). |
| RS023 | Filler docstring opening: a docstring whose summary opens with `This function`, `This method`, `This class`, `This module`, `Helper to`, `Helper for`, `Used to`, `Simply`, or `Just` restates the identifier instead of stating the contract. |

### Repo-agnostic vs repo-specific

Most rules are repo-agnostic and safe to enable anywhere. Two are tied to the fhir-ingestor hexagonal architecture and its test conventions, and other repos (for example a Beam monorepo) should NOT select them:

- **RS002** assumes PascalCase test naming under `tests/unit/`. Repos with a different test-naming convention should not select it.
- **RS006** bans concrete implementation libraries inside a `src/fhir_ingestor/application/ports/` path. The path fragment and the hexagonal `ports` layering are fhir-ingestor-specific.

RS003 (mock ban) is also somewhat opinionated, since it presumes a `tests/fakes/` directory; enable it only where that convention holds. The rest (RS001, RS004, RS005, RS007, RS008, RS009, RS010, RS011) are general style rules.

The test-quality rules (RS013–RS016) apply only to `test`-prefixed functions in test files, so they are inert elsewhere. RS012, RS015, RS016, RS018, RS019, RS020, and RS021 are advisory: they emit a `warning` and do not fail the run, since their signals are heuristics that mark where to look rather than assert a defect. RS013, RS014, RS022, and RS023 are mechanical and hard-fail. The documentation-form rules (RS020, RS021, and RS023) are general style rules.

## Consume as a pre-commit remote hook

Add to the consuming repo's `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/gradienthealth/gradient-pystyle
    rev: gradient-pystyle-v0.1.0
    hooks:
      - id: gradient-pystyle
```

The hook runs the `gradient-pystyle` console script over the staged Python and markdown files.

## Select rules per repo

The runner reads the consuming repo's `pyproject.toml`:

```toml
[tool.gradient-pystyle]
select = ["RS001", "RS004", "RS005", "RS007", "RS008", "RS009", "RS010", "RS011"]
ignore = []
```

Enabled rules are `select` minus `ignore`. If the table is missing or empty, all rules are enabled. The nearest `pyproject.toml` is discovered by walking up from the first target path's directory.

## Configure layering bans (RS017)

RS017 takes its bans from config, so each repo expresses its own layering. Map a path glob (relative to the repo root, `fnmatch` semantics) to the import sources files under it may not import:

```toml
[tool.gradient-pystyle.banned-imports]
"src/**" = ["tests"]
"**/application/ports/**" = ["httpx", "sqlalchemy", "psycopg", "boto3", "google.cloud.bigquery"]
```

A file matching a glob that imports a banned source — or a submodule of it (`tests.fakes`) — is flagged. Relative imports are left to the no-relative-imports ruff rule. With no table, RS017 reports nothing, so selecting it is harmless until a layer is configured.

## Configure comment tags (RS022)

RS022 holds a special comment to `TAG(TICKET): message`. The allowed tag set and the ticket pattern are config-driven, so a repo expresses its own ticket shape; both fall back to a default when omitted:

```toml
[tool.gradient-pystyle]
comment-tags = ["TODO", "FIXME", "NOTE", "HACK"]
comment-ticket-pattern = "[A-Z]+-\\d+|NO-ISSUE"
```

A comment whose leading token is an allowed tag, or a known alias of one (`XXX`, `BUG`, `TBD`, ...), is held to the canonical form; the alias steers toward the first allowed tag. A deviation — an unknown tag, wrong casing, a missing or malformed ticket, or a wrong separator — is flagged. A comment whose leading token is neither a tag nor an alias is ordinary prose and is left alone. The default ticket pattern is the Linear-id shape plus the literal `NO-ISSUE`.

## Suppress a finding

To waive a single finding without disabling the rule repo-wide, add an inline directive:

- `# style: ignore[RS010]` — drop the named rule on that line (comma-separate to list several: `# style: ignore[RS001, RS011]`).
- `# style: ignore` — drop every rule's findings on that line.
- `# style: ignore-file` — drop every finding in the file; place it anywhere in the file.

The `style` token, rather than ruff's `noqa`, keeps these from colliding with ruff's own suppression handling.

## Scope findings to changed lines

Adopting a rule should not mean fixing the whole existing codebase first. Run with `--diff` to report only findings on lines the change touched:

```bash
gradient-pystyle --diff --diff-base origin/main $(git diff --name-only origin/main)
```

`--diff` intersects each finding's line with the lines that differ from `--diff-base` (default `HEAD`); a finding on an untracked file or one that cannot be diffed is reported in full, so nothing is hidden by accident. The intersection is on the finding's own line, so a whole-unit finding (a complexity rule reported at the `def`) re-arms only when that line itself changes.

This scopes gradient-pystyle's own `RSnnn` rules. Ruff has no diff mode, so to scope the ruff rules to a PR's lines, filter ruff's output in CI with [reviewdog](https://github.com/reviewdog/reviewdog) (`-filter-mode=added`) or graylint locally.

## Rewrap docstrings and comments

`RS009` flags docstring and comment paragraphs that are not filled to 72 columns. Run with `--fix` to rewrap them in place instead of only reporting:

```bash
gradient-pystyle --fix $(git diff --name-only)
```

`--fix` greedily refills each paragraph at its hanging indent, leaving verbatim structures (code fences, doctests, tables, rules, section headers) untouched and respecting `# style: ignore` directives. It exits non-zero when it changed a file, so a pre-commit run stops and you re-stage the rewrapped files. `RS009` is the only fixable rule today.

## Extend the base ruff config

`ruff-base.toml` is the shared baseline (line length 88, double-quote format, the `select`/`ignore` set, Google pydocstyle, banned relative imports, 88-column doc lines). Extend it from the consuming repo's `pyproject.toml`:

```toml
[tool.ruff]
extend = "path/to/ruff-base.toml"
target-version = "py311"
```

Override only repo-specific knobs (target version, per-file ignores) on top of the inherited baseline.

## Check docstrings against signatures

The base config enforces docstring *style* (Google convention, via the ruff `D` rules) but not that a docstring's `Args`/`Returns`/`Raises` match the actual signature — ruff's `D` rules don't check that. Add [pydoclint](https://github.com/jsh9/pydoclint) as a pre-commit hook in the consuming repo to catch that drift:

```yaml
  - repo: https://github.com/jsh9/pydoclint
    rev: ""  # pin to a pydoclint release tag
    hooks:
      - id: pydoclint
        args: [--style=google]
```

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```
