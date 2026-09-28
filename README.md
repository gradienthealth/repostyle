# repostyle

`repostyle` enforces repository conventions that ruff cannot express. It ships 67 `RSnnn` rules, a shared ruff configuration, and optional hooks for the house lint gate suite.

The linter has no runtime dependencies. Most rules inspect Python with the standard-library AST and tokenizer. Comment rules also inspect `#` comments in TOML, YAML, and shell files.

## Install

```bash
pip install repostyle
pip install "repostyle[gates]" # Include the pinned third-party gate tools.
```

Run it without installing with `uvx repostyle .`.

## Add the pre-commit hook

```yaml
repos:
  - repo: https://github.com/gradienthealth/repostyle
    rev: repostyle-vX.Y.Z # Pin the latest release tag.
    hooks:
      - id: repostyle
```

The hook checks staged Python, Markdown, TOML, YAML, and shell files. A repo can select rules and tune their behavior in `pyproject.toml`:

```toml
[tool.repostyle]
select = ["RS001", "RS004", "RS005", "RS009", "RS010"]
ignore = []
error = ["RS034"]
warnings-as-errors = false
```

An absent or empty table enables every rule. `select` minus `ignore` determines the enabled set. `error` promotes specific advisory rules, while `warnings-as-errors` promotes every warning.

## Common commands

```bash
repostyle .                         # Check a tree.
repostyle --fix .                   # Apply safe mechanical fixes.
repostyle --no-baseline .           # Include grandfathered findings.
repostyle --write-baseline .        # Record an inherited backlog.
repostyle --update-baseline .       # Remove fixed debt from the record.
repostyle explain RS010             # Show one rule's guidance.
repostyle explain --all             # Show every rule card.
```

`--fix` returns a non-zero status when it changes a file so pre-commit can stop for review and restaging.

## Documentation

| Guide | Use it for |
| -- | -- |
| [Rule reference](docs/rules.md) | Rule ids, severities, scope, and ruff overlap. |
| [Configuration](docs/configuration.md) | Selection, baselines, exclusions, suppressions, fixers, and per-rule settings. |
| [Gate suite](docs/gates.md) | The shared ruff base and optional third-party hooks. |
| [Judgment conventions](docs/judgment-conventions.md) | Review decisions that a linter cannot make. |
| [Google Cloud naming](docs/gcp-naming.md) | Resource identifiers and current product names. |
| [Development](docs/development.md) | Local setup, architecture, testing, and releases. |

A finding carries the short remediation. Run `repostyle explain RSnnn` when a rule needs rationale or examples.

## License

Apache-2.0. See [LICENSE](LICENSE).
