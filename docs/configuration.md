# Configuration

`repostyle` reads its settings from the nearest config file above the first target path: a `repostyle.toml`, which holds them at its top level, or a `pyproject.toml`, which holds them under `[tool.repostyle]`. A directory holding both uses `repostyle.toml`, so a repository without Python packaging, such as a Java service, configures the linter without a `pyproject.toml`. The examples below use the `pyproject.toml` form. An absent or empty table enables every rule.

## Select and promote rules

```toml
[tool.repostyle]
select = ["RS001", "RS004", "RS009", "RS034"]
ignore = ["RS004"]
error = ["RS034"]
warnings-as-errors = false
```

The enabled set is `select` minus `ignore`. `error` promotes selected warnings. `warnings-as-errors` promotes every warning. The command-line `--warnings-as-errors` and `--no-warnings-as-errors` flags override the file.

## Choose languages

```toml
[tool.repostyle]
languages = ["python", "markdown", "toml", "yaml", "shell", "java"]
```

`languages` lists every language `repostyle` reads, replacing the default of `python`, `markdown`, `toml`, `yaml`, and `shell`. Java is opt-in while its rules settle, so a release that adds Java checks reaches only repositories that listed it. A file in an unlisted language is skipped whether it was walked or passed explicitly, and an unknown name is a configuration error.

Set `assertion-library` to `truth` (the default), `assertj`, or `junit` to choose the one library RS071 lets Java tests assert with.

Java comments fill to google-java-format's 100 columns rather than 79, a `// style: ignore[RSnnn]` comment suppresses a finding as `#` does, and Maven's `target/` output beside a `pom.xml` is pruned with the other build directories.

## Baseline inherited findings

Create a baseline when a repository adopts rules with existing debt:

```bash
repostyle --write-baseline .
```

The command writes `.repostyle-baseline.json` beside `pyproject.toml`. It counts findings per file and rule instead of storing line numbers, so ordinary edits do not revive unchanged debt.

After fixes, lower the recorded counts:

```bash
repostyle --update-baseline .
```

An update never raises the count for a known rule, but it can admit findings from rules added after the baseline. A partial scan preserves records for unscanned files. Use `--no-baseline` to audit the full tree.

Set `baseline = "path/to/file.json"` to use another location.

## Opt out of a baseline

A repository that keeps zero findings can refuse a baseline outright:

```toml
[tool.repostyle]
baseline = false
warnings-as-errors = true
```

With `baseline = false`, runs ignore any `.repostyle-baseline.json`, so delete one the repository already holds. The `--write-baseline` and `--update-baseline` flags exit with status 2 without writing. The baseline sync workflow skips the repository and closes its open refresh pull request, so findings from rules added in a new release fail the build instead of being grandfathered. Any value other than a nonempty path or `false` is a configuration error.

## Exclude generated and ignored paths

```toml
[tool.repostyle]
exclude = ["*_pb2.py", "vendor/*"]
respect-gitignore = true
```

`exclude` uses `fnmatch` against paths relative to `pyproject.toml`; `*` can span `/`. Excluded files remain visible to package-wide analysis but emit no findings. `respect-gitignore` prunes directories matched by the root `.gitignore`, so their files are absent from package-wide analysis too.

The gitignore reader supports comments, blank lines, directory names, leading root anchors, and `fnmatch` globs. It does not read nested `.gitignore` files. An unbounded negation disables pruning rather than risking an incorrect scan; use `exclude` when exact behavior matters.

Version-control metadata, caches, virtual environments, `node_modules`, build outputs such as `build/` and a Maven `target/` beside its `pom.xml`, and nested Git checkouts are always pruned during directory walks. Explicit file arguments remain lintable.

## Configure scoped rules

```toml
[tool.repostyle]
test-naming-globs = ["tests/unit/test_*.py"]
port-path-globs = ["src/*/application/ports/*.py"]

[tool.repostyle.banned-imports]
"src/*/domain/*.py" = ["django", "requests"]
```

`test-naming-globs` scopes RS002. `port-path-globs` scopes RS006. The `banned-imports` keys scope RS017 and their values name forbidden import roots.

## Configure names and prose

```toml
[tool.repostyle]
acronyms-extra = ["DICOM"]
acronyms-exclude = ["SMART"]
comment-tags = ["TODO", "FIXME", "NOTE"]
comment-ticket-pattern = "PROC-\\d+"
imperative-verbs-extra = ["Deploy"]
imperative-verbs-exclude = ["Cache"]
```

The `extra` lists extend the built-ins; the `exclude` lists remove entries from the combined set. RS001 and RS049 share the acronym configuration. RS022 uses the comment-tag and ticket settings. RS034 uses the imperative-verb settings.

## Configure the public surface

```toml
[tool.repostyle]
public-names = ["handler"]
public-modules = ["src/*/api.py"]
public-decorators = ["fixture"]
```

RS029 also treats `__all__`, package re-exports, and `[project.scripts]` entry points as public. `public-decorators` matches the decorator's final attribute, so `fixture` covers both `@fixture` and `@pytest.fixture`.

## Configure filenames

```toml
[tool.repostyle]
filename-case = "kebab"
filename-ignore = ["Makefile"]

[tool.repostyle.filename-extensions]
".yml" = ".yaml"
```

The extension table replaces the default map. Declare it empty to disable the extension check. `filename-case = "none"` disables casing. RS033 always skips Python files and recognizes fixed ecosystem names such as `README.md`, `CHANGELOG.md`, `CLAUDE.md`, and `AGENTS.md`.

## Configure module-size review points

```toml
[tool.repostyle]
max-test-file-lines = 500
max-source-file-lines = 250
```

RS062 and RS066 count physical code lines. Blank lines, comment-only lines, module, class, and function docstrings, and field docstrings do not count. Choose a larger positive limit only when a cohesive registry or matrix would become harder to navigate after a split.

## Suppress a finding

Use the narrowest directive that carries a durable reason:

```python
value = parse(raw)  # style: ignore[RS010]

# style: ignore-block[RS012]
def parse_bundle(raw: str) -> Bundle:
    ...

# style: ignore-file[RS066]
```

Omit the brackets to suppress every rule in the directive's scope. A block directive covers the next Python statement, including decorators and its body, or the next YAML folded scalar. In other file types it falls back to its own line.

## Fix safe findings

```bash
repostyle --fix .
```

The fixer supports these rules:

| Rule | Rewrite |
| -- | -- |
| RS005 | Converts double-backtick code spans to single backticks. |
| RS009 | Refills prose at its existing hanging indent. |
| RS030 | Adds terminal punctuation. |
| RS049 | Restores canonical acronym casing. |
| RS050 | Uses the current Google Cloud term. |
| RS054 | Uses the spaced `--` sentence dash. |
| RS058 | Uses the canonical docstring section header. |
| RS061 | Collapses double spaces after sentence-ending punctuation. |

RS009 skips code fences, doctests, tables, preformatted lines, YAML literal scalars, expressions, and suppressed prose. It can reflow a YAML folded scalar when that scalar reads as prose and ends in terminal punctuation.

## Explain findings

```bash
repostyle explain RS010
repostyle explain --all
```

The card expands the short finding into its contract, rationale, examples, and references. Use `--no-explain-hint` to hide the pointer printed after findings.

## Legacy changed-line mode

`--diff` is deprecated. It intersects finding lines with a Git diff and needs the base commit available locally. Baselines handle inherited debt without hiding findings on untouched lines, so new integrations should use them.
