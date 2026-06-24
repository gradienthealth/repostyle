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

### Repo-agnostic vs repo-specific

Most rules are repo-agnostic and safe to enable anywhere. Two are tied to the fhir-ingestor hexagonal architecture and its test conventions, and other repos (for example a Beam monorepo) should NOT select them:

- **RS002** assumes PascalCase test naming under `tests/unit/`. Repos with a different test-naming convention should not select it.
- **RS006** bans concrete implementation libraries inside a `src/fhir_ingestor/application/ports/` path. The path fragment and the hexagonal `ports` layering are fhir-ingestor-specific.

RS003 (mock ban) is also somewhat opinionated, since it presumes a `tests/fakes/` directory; enable it only where that convention holds. The rest (RS001, RS004, RS005, RS007, RS008, RS009, RS010, RS011) are general style rules.

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
