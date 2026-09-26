# Lint gate suite

The repository distributes two related layers:

- `ruff-base.toml` defines the shared ruff rule and formatter baseline.
- The `repostyle-*` hooks and `repostyle[gates]` extra pin third-party tools at one version for every consuming repository.

## Extend the ruff base

```toml
[tool.ruff]
extend = "path/to/ruff-base.toml"
target-version = "py311"
```

Keep only repository-specific settings, such as the Python target and per-file ignores, in the consuming repository.

## Use exported pre-commit hooks

```yaml
repos:
  - repo: https://github.com/gradienthealth/repostyle
    rev: repostyle-vX.Y.Z
    hooks:
      - id: repostyle
      - id: repostyle-bandit
      - id: repostyle-vulture
      - id: repostyle-deptry
      - id: repostyle-interrogate
      - id: repostyle-codespell
      - id: repostyle-shellcheck
      - id: repostyle-shfmt
```

One `rev` update moves the complete suite. Python tools read their own tables from the consuming repository's `pyproject.toml`:

```toml
[tool.bandit]
exclude_dirs = ["tests"]

[tool.interrogate]
fail-under = 30
ignore-init-method = true
ignore-init-module = true
ignore-magic = true
ignore-private = true
ignore-semiprivate = true
ignore-nested-functions = true
exclude = ["tests"]

[tool.vulture]
paths = ["src", "vulture_whitelist.py"]
min_confidence = 80
ignore_decorators = ["@pytest.fixture", "@pytest.mark.parametrize"]
ignore_names = ["model_config", "exc_type", "exc_val", "exc_tb"]

[tool.deptry]
known_first_party = ["your_package"]

[tool.codespell]
skip = "uv.lock,*.svg,.git"
ignore-words-list = "datas,ehr,fo,hist"
```

Shellcheck reads `.shellcheckrc`. The exported shfmt hook runs `shfmt -d -i 2 -ci`; a repository can override the indentation with later hook arguments.

## Use the package extra

A repository that already installs its lint environment can use the same pins without exported hooks:

```toml
[dependency-groups]
lint = ["repostyle[gates]>=X.Y.Z"]
```

Keep local pre-commit hooks that run each tool through that environment. Give shfmt the same `-d -i 2 -ci` arguments if the repository wants the house default.

## Keep environment-dependent gates local

The suite does not export mypy, pyright, or pip-audit. Type checkers need the consuming project's installed dependencies, and pip-audit needs its resolved dependency graph. Run those tools in the consuming repository's environment.

Pydoclint also stays consumer-side when a project wants signature-to-docstring validation; ruff and repostyle enforce the docstring form but do not compare every section with a callable's signature.
