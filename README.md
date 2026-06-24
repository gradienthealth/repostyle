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

## Extend the base ruff config

`ruff-base.toml` is the shared baseline (line length 88, double-quote format, the `select`/`ignore` set, Google pydocstyle, banned relative imports, 88-column doc lines). Extend it from the consuming repo's `pyproject.toml`:

```toml
[tool.ruff]
extend = "path/to/ruff-base.toml"
target-version = "py311"
```

Override only repo-specific knobs (target version, per-file ignores) on top of the inherited baseline.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```
