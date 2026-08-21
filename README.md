# repostyle

repostyle is a linter for the house style conventions that ruff does not cover. It ships 61 rules, each with an `RSnnn` id, and a shared ruff base config. Every consuming repo picks the subset it wants and runs it as a pre-commit hook.

The linter is stdlib-only, so installing it pulls in nothing. It reads Python through the `ast` module and the tokenizer. Most rules are Python-specific, but the comment rules also read `#` comments in TOML, YAML, and shell files, so a comment is held to the same conventions whatever the language.

These rules are the mechanical half of the house style. The judgment half — conventions a tool cannot decide — lives in [`docs/judgment-conventions.md`](docs/judgment-conventions.md), which each repo references rather than restating.

## Install

```bash
pip install repostyle           # the linter alone
pip install "repostyle[gates]"  # plus the pinned third-party gate tools
```

You can also run it without installing: `uvx repostyle .`.

## Use it as a pre-commit hook

Add this to the consuming repo's `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/gradienthealth/repostyle
    rev: repostyle-vX.Y.Z # pin to the latest repostyle-v release tag
    hooks:
      - id: repostyle
```

The hook runs the `repostyle` console script over the staged Python, markdown, TOML, YAML, and shell files.

## Rules

Each rule has an `RSnnn` id, and a repo selects or ignores rules by id. The tables below give a one-line summary of each. For the full contract, the rationale, and before-and-after examples, run `repostyle explain RSnnn`.

The **Default** column is the severity that applies when a repo sets `warnings-as-errors = false`. Without that opt-out, every selected rule fails the run. See [Severity](#severity) below.

### Naming

| Rule | Default | What it checks |
| -- | -- | -- |
| RS001 | error | A known acronym stays all-uppercase in a CapWords name (`FHIRClient`, not `FhirClient`). |
| RS010 | error | Spell names out. A known abbreviation in an introduced name is rejected. |
| RS011 | error | A class is named for its responsibility, not a vague `Manager`, `Helper`, or `Util` role. |
| RS024 | warning | A boolean name does not embed `not` or `no`. Name the positive and negate at the call site. |
| RS025 | error | `make_` is for test fixtures. Production code uses `build_` for in-memory assembly or `create_` for a side effect. |
| RS026 | warning | A `bool`-annotated name reads as a yes/no question: `is_`, `has_`, `can_`, or `should_`. |
| RS028 | error | An `except ... as` alias is `exc`, `exc2` when nested, or a descriptive name. Never `e`, `ex`, or `err`. |
| RS044 | warning | A `-> bool` function named as a bare state word reads as a question instead (`is_valid`, not `valid`). |
| RS051 | warning | A string parameter named for a Google Cloud resource collection carries the `_id` suffix (`project_id`). |

### Docstring content

| Rule | Default | What it checks |
| -- | -- | -- |
| RS004 | error | A dataclass documents its fields with per-field docstrings, not a Google `Attributes:` block. |
| RS018 | warning | A non-trivial public function is under-documented: no docstring, or a tuple return with no `Returns:` section. |
| RS020 | warning | A leading summary comment on a definition should be its docstring. |
| RS021 | warning | A dataclass field's explanatory comment should be a field docstring. |
| RS023 | error | A docstring opens with the unit's contract, not a filler phrase such as `This function ...`. |
| RS031 | warning | Per-argument detail goes in an `Args:` section, not narrated in the body. |
| RS032 | warning | The return value goes in a `Returns:` section, not narrated in the body. |
| RS034 | warning | A docstring summary opens descriptively (`Returns the lease.`), not imperatively (`Return the lease.`). |
| RS041 | warning | A raised exception goes in a `Raises:` section, not narrated in the body. |
| RS043 | warning | A `Raises:` section lists every exception the body raises outright. |

### Docstring sections

| Rule | Default | What it checks |
| -- | -- | -- |
| RS047 | warning | An `Args:`, `Returns:`, `Raises:`, or `Yields:` entry description opens with a capital letter. |
| RS056 | warning | A section header comes from the recognized Google set, never an invented or Sphinx-imported one. |
| RS057 | warning | Sections run in the canonical order: `Args:`, then `Returns:` or `Yields:`, then `Raises:`, then `Example:`. |
| RS058 | warning | A section header uses the canonical spelling: `Args:`, not `Arguments:`; `Returns:`, not `Return:`. |
| RS059 | warning | A docstring holds at most one section per family. A second `Args:` merges into the first. |

### Prose style

These rules read docstrings and comments alike. The comment half of each runs over Python, TOML, YAML, and shell files.

| Rule | Default | What it checks |
| -- | -- | -- |
| RS005 | error | Prose uses single backticks for a code span, never double. |
| RS009 | error | A docstring, comment, or YAML folded-scalar paragraph fills to 79 columns. |
| RS030 | warning | A prose unit ends with terminal punctuation: `.`, `!`, or `?`. |
| RS035 | warning | A docstring summary line fits within 79 columns. |
| RS036 | warning | A docstring wraps a code name it references in single backticks. |
| RS037 | warning | A code span ends on a word boundary. No suffix is glued to the closing backtick. |
| RS039 | warning | Where a block backticks one code symbol, its sibling code tokens are backticked too. |
| RS045 | warning | Prose states the code's present contract, not how it changed (`previously`, `used to`, `for now`). |
| RS049 | warning | A known acronym keeps its canonical casing (`IPv6`, not `ipv6`; `NAT`, not `Nat`). |
| RS050 | warning | A Google Cloud product or brand name is current (`Cloud Storage`, not `GCS`; `Google Cloud`, not `GCP`). |
| RS053 | warning | A bulleted list holding a multi-sentence item opens every item with a capital letter. |
| RS054 | warning | A clause is set off with the house sentence dash, the spaced `--`, not an em dash, en dash, or hyphen. |
| RS061 | warning | A single space follows sentence-ending punctuation, not the old typewriter double space. |

### Comments

| Rule | Default | What it checks |
| -- | -- | -- |
| RS022 | error | A special comment reads `TAG(TICKET): message`, with an allowed tag and a tracking ticket. |
| RS038 | warning | A wrapped tag comment indents its continuation past the tag. A separate note is set off by a blank line. |
| RS055 | warning | No banner, divider, or framed-title comments. Express the grouping with structure instead. |

### Tests

| Rule | Default | What it checks |
| -- | -- | -- |
| RS002 | error | A unit test is named `test_StateUnderTest_ExpectedBehavior`. |
| RS003 | error | `unittest.mock` and `mock` are rejected outside `tests/fakes/`. Use a port fake. |
| RS013 | error | A test keeps its asserted path straight-line, not wrapped in an `if`, `for`, `while`, or `try`. |
| RS014 | error | A test does not call `time.sleep` or `asyncio.sleep`. Wait on a condition or fake the clock. |
| RS015 | warning | A test builds more than three mocks, a density signal of brittle coupling. |
| RS016 | warning | A test asserts only call choreography (`assert_called*`) and never state. |
| RS060 | warning | A test asserts only literals it read from a single repo file, exercising nothing beyond the parser. |

### Functions and classes

| Rule | Default | What it checks |
| -- | -- | -- |
| RS012 | warning | A function's cognitive complexity is over the limit of 15. |
| RS019 | warning | Module and class members run top-down by dependency, then alphabetically for free choices. |
| RS027 | warning | A function takes at most five positional parameters. Pass the rest as keywords. |
| RS040 | warning | A type annotation nests subscripted generics past two levels. Name the buried type. |
| RS042 | error | A class defines `__eq__` and `__hash__` as a pair, or neither. |
| RS046 | warning | A `for i in range(len(seq))` loop that only indexes `seq[i]` should iterate `seq` directly. |
| RS052 | warning | An `except` tuple does not reach past the failure it was written for, into the structural builtins. |

### Imports and visibility

| Rule | Default | What it checks |
| -- | -- | -- |
| RS006 | error | A port module declares contracts only. It holds no implementation. |
| RS017 | error | A file does not import a module its layer's `banned-imports` config forbids. |
| RS029 | warning | A symbol used only inside its own package carries a leading underscore. |
| RS048 | warning | A first-party import consumes another package's public surface, not its `_`-private internals. |

### Values and files

| Rule | Default | What it checks |
| -- | -- | -- |
| RS007 | error | A module-level duration is a `timedelta`, not a raw `*_SECONDS` number. |
| RS008 | error | A PHI-safe logger call passes no `exc_info`. A traceback can carry PHI past the redaction. |
| RS033 | warning | A non-Python file uses the configured extension and casing. The default is `.yaml` over `.yml` and kebab-case. |

### Which rules to enable

Most rules are repo-agnostic and safe to enable anywhere. Three assume a particular layout:

| Rule | Assumes | Re-scope with |
| -- | -- | -- |
| RS002 | PascalCase test names under `tests/unit/` | `test-naming-globs` |
| RS003 | a `tests/fakes/` directory holding the fakes | — |
| RS006 | a hexagonal port layer at `application/ports/` | `port-path-globs` |

A repo that keeps the same convention in another place re-scopes the rule with the config key. A repo that does not share the convention at all should leave the rule out.

RS017 reports nothing until a `banned-imports` table names its bans, so selecting it early is harmless.

The test rules (RS002, RS003, RS013 through RS016, and RS060) only examine test functions in test files, so they are inert everywhere else.

### Severity

Every selected rule fails the run. A repo gates on the rule set it chose, not on a severity split it did not, so adding an id to `select` is the whole decision. Pre-existing findings are held by the [baseline](#grandfather-the-existing-backlog) rather than by a softer severity.

A repo can opt out with `warnings-as-errors = false`, which restores the per-rule default severities shown in the tables above. Under those defaults 19 rules hard-fail and the other 42 print as warnings:

```
RS001  RS002  RS003  RS004  RS005  RS006  RS007  RS008  RS009  RS010
RS011  RS013  RS014  RS017  RS022  RS023  RS025  RS028  RS042
```

Those 19 are the mechanical rules whose findings are objective. The rest warn for one of two reasons.

Some are heuristics that mark where to look rather than assert a defect, so a human decides. Those are the complexity and threshold rules (RS012, RS027, RS040), the test-quality signals (RS015, RS016, RS060), the documentation-value signals (RS018, RS020, RS021), and the layout and encapsulation smells (RS019, RS029, RS048, RS052).

The others are simply new. They warn until their false-positive rate on the existing repos has been measured.

A run that tolerated warnings closes with a count on stderr, so an advisory backlog is never silent:

```
repostyle: 12 warning(s) reported without failing the run
```

The `--warnings-as-errors` and `--no-warnings-as-errors` flags override the config for a single run without touching it.

### Rules standing in for preview-gated ruff rules

Two rules duplicate a ruff rule that is still behind ruff's preview gate. Enabling either through ruff would mean setting `preview = true` in the shared `ruff-base.toml`, which turns on preview behavior for every rule and the formatter across all consuming repos. They live here instead until the ruff rules graduate.

RS027 mirrors [`PLR0917`](https://docs.astral.sh/ruff/rules/too-many-positional-arguments/) exactly: the cap of five, the positional-only counting, the `self` and `cls` exclusion, and the `@override` exemption. A keyword-only parameter never counts, so a keyword-only builder is left alone. When `PLR0917` goes stable, select it in `ruff-base.toml` and delete RS027 (PROC-2319). Note that `PLR0917` is a hard error, so adopting it raises the severity.

RS042 goes further than [`PLW1641`](https://docs.astral.sh/ruff/rules/eq-without-hash/), which flags only `__eq__` without `__hash__`. RS042 flags `__hash__` without `__eq__` as well. When `PLW1641` goes stable, select it in `ruff-base.toml` and drop RS042's eq-without-hash half, keeping the other half here.

## Select rules per repo

The runner reads the consuming repo's `pyproject.toml`. It finds the nearest one by walking up from the first target path's directory.

```toml
[tool.repostyle]
select = ["RS001", "RS004", "RS005", "RS007", "RS008", "RS009", "RS010", "RS011"]
ignore = []
warnings-as-errors = false # opt out: restore the per-rule severities
error = ["RS034", "RS035"] # then promote these advisory rules to hard-fail
```

Enabled rules are `select` minus `ignore`. If the table is missing or empty, every rule is enabled.

`error` names the advisory rules to promote once the repo has opted out of the error-by-default mode. It is the surgical option: a repo gates on a trusted subset while leaving the heuristic rules advisory. Promoting a disabled rule is inert, and promoting a rule that already fails by default is a harmless no-op. An unknown id is rejected the same way `select` and `ignore` validate theirs.

## Grandfather the existing backlog

A repo adopting a rule inherits whatever its tree already violates, and that backlog is nobody's regression. Record it once:

```bash
repostyle --write-baseline .
```

That writes `.repostyle-baseline.json` beside the repo's `pyproject.toml`, holding how many findings of each rule each file already had. Later runs report only the findings above those counts, so new code meets the full standard while the existing tree is left alone. The file is found by name, so nothing else needs configuring. Point `[tool.repostyle] baseline` at another path to keep it elsewhere.

The record counts findings per file per rule and never stores a line number. Editing a file therefore does not resurrect its grandfathered findings, and the baseline does not go stale on churn alone.

Refresh it after clearing debt:

```bash
repostyle --update-baseline .
```

A refresh lowers a count to what the tree now holds, so a fix is permanent. It admits the backlog of rules the baseline predates, so a release that adds rules does not redden the build.

A refresh never raises a count for a rule the baseline already knew, so new code cannot grandfather itself by refreshing. A file the run did not scan keeps its counts, so refreshing part of a tree does not strip the rest.

The `sync repostyle baselines` workflow runs a refresh across the consuming repos after each release and opens the pull request.

Pass `--no-baseline` to report every finding and ignore the record. That is how a repo measures the debt it still carries.

## Exclude paths from scanning

`exclude` drops a file from linting entirely, so generated or vendored code stays out of the scan:

```toml
[tool.repostyle]
exclude = ["*_pb2.py", "*_pb2_grpc.py", "vendor/*"] # globs skipped by every rule
```

The globs use `fnmatch` semantics and match against the path relative to the discovered `pyproject.toml`. In `fnmatch` a `*` spans `/` and there is no recursive `**` operator, so a name glob like `*_pb2.py` already matches at any depth. To exclude a `_grpc` directory wherever it sits, write `*_grpc/*.py` rather than `**/_grpc/*.py`.

An excluded file is dropped however it reaches repostyle, whether walked from a directory argument or passed by name, so the pre-commit hook cannot re-flag a regenerated file. With no `exclude` configured, every discovered file is scanned.

`exclude` is a global discovery filter. It is distinct from `filename-ignore`, which only exempts a file from RS033 and leaves every other rule to scan it.

## Skip gitignored trees

A repo already lists its vendored and generated trees in `.gitignore`. Rather than restate each one in `exclude`, set `respect-gitignore` and repostyle prunes any directory the root `.gitignore` names:

```toml
[tool.repostyle]
respect-gitignore = true # prune directories the root .gitignore names
```

The root `.gitignore` is the one beside the discovered `pyproject.toml`. The flag is off by default, so no existing repo's behavior changes and a repo that gitignores a path it does want linted is not surprised.

A gitignored path is treated as not part of the repo at all. A pruned directory is invisible to every rule, including the RS029 whole-package visibility index.

That is the deliberate split from `exclude`, which keeps a file in the tree and silences only its findings. A generated stub kept by `exclude` still counts as a cross-module reference for RS029. A gitignored one does not.

### The supported `.gitignore` subset

The matcher honors enough of `.gitignore` syntax for the vendored-tree case:

- Blank lines and `#` comments are skipped.
- A trailing-slash `foo/` and a bare `foo` both name a directory.
- A leading-slash `/foo` or an internal-slash `foo/bar` anchors to the repo root. A bare name matches a directory so named at any depth.
- Glob matching is `fnmatch`, the same as the `exclude` globs, so `*` spans `/`.

Two constructs are deliberately unsupported. The first is the `!` negation, which is never honored as a re-inclusion. An anchored one only spares its own subtree from pruning. An unanchored one switches gitignore pruning off for the whole repo, because its any-depth reach cannot be bounded cheaply.

The second is a per-directory `.gitignore` below the root, which is not read at all. Where either bound matters, use `exclude`, which is unaffected.

### Structural pruning

Some directories are pruned whatever `respect-gitignore` says: version-control metadata, caches, `venv`, `node_modules`, build outputs, and any directory holding its own `.git`.

That last one stops a nested checkout being walked as part of the outer repo, most often a `git worktree` parked under `.claude/`. Walking a second copy also silences RS029, because the copy of a module counts as another module referencing the original's names.

The nested-checkout prune has no opt-out, but it only prunes a directory *below* the walk root, so a nested checkout stays lintable two ways:

- Name one of its files explicitly. A file argument bypasses the walk.
- Run repostyle from inside the checkout. Its own root is never pruned.

Neither adds the tree back to the outer repo's cross-module index. To keep a name public that only a nested checkout references, list it in `public-names`.

## Configure individual rules

### Acronyms (RS001, RS049)

RS001 checks a fixed set of acronyms (`API`, `FHIR`, `HTTP`, `ID`, `JWT`, `URL`, and others) in CapWords names, and RS049 holds the same set in docstring and comment prose. A repo whose domain carries its own acronyms tunes the set without a repostyle source change:

```toml
[tool.repostyle]
acronyms-extra = ["UID", "SCU", "SCP", "PACS"] # domain acronyms this repo's names use
acronyms-exclude = ["DOB"]                     # a shipped acronym too aggressive here
```

`acronyms-extra` adds to the shipped set rather than replacing it. `acronyms-exclude` removes from the combined result, so it can drop a shipped acronym, an added one, or both. Neither key needs the other.

RS001 matches entries uppercased, so their case in the config does not matter. RS049 treats an `acronyms-extra` entry's own casing as the canonical form prose is rewritten to, so write `IPv4` to have `ipv4` corrected to `IPv4`. RS049 also drops any shipped acronym whose lowercase doubles as a common English word, such as `SMART` and `ID`, from its prose set. An `acronyms-extra` entry overrides that.

### Layering bans (RS017)

RS017 takes its bans from config, so each repo expresses its own layering. Map a path glob to the import sources that files under it may not import:

```toml
[tool.repostyle.banned-imports]
"src/**" = ["tests"]
"**/application/ports/**" = ["httpx", "sqlalchemy", "psycopg", "boto3", "google.cloud.bigquery"]
```

Globs are relative to the repo root and use `fnmatch` semantics. A file matching a glob that imports a banned source, or a submodule of it such as `tests.fakes`, is flagged. Relative imports are left to ruff's own no-relative-imports rule. With no table, RS017 reports nothing, so selecting it is harmless until a layer is configured.

### Comment tags (RS022)

RS022 holds a special comment to `TAG(TICKET): message`. Both the allowed tag set and the ticket pattern are config-driven, and both fall back to a default when omitted:

```toml
[tool.repostyle]
comment-tags = ["TODO", "FIXME", "NOTE", "HACK"]
comment-ticket-pattern = "[A-Z]+-\\d+|NO-ISSUE"
```

A comment whose leading token is an allowed tag, or a known alias such as `XXX`, `BUG`, or `TBD`, is held to the canonical form. An alias steers toward the first allowed tag. An unknown tag, wrong casing, a missing or malformed ticket, or a wrong separator is flagged.

A comment whose leading token is neither a tag nor an alias is ordinary prose and is left alone. The default ticket pattern is the Linear id shape plus the literal `NO-ISSUE`.

### Filenames (RS033)

RS033 checks a non-Python file's extension and casing, and ships a default for each rather than reporting nothing until configured. The extension default is `.yaml` over `.yml`, which yaml.org has recommended since 2006. The casing default is kebab-case for a multi-word name, which Google's developer documentation style guide prefers because a search engine reads a hyphen as a word break and an underscore not.

```toml
[tool.repostyle]
filename-case = "kebab"                       # or "snake", or "none" to disable
filename-ignore = [".github/workflows/*.yml"] # globs exempted from both checks

[tool.repostyle.filename-extensions]
".yml" = ".yaml"
```

A curated set of fixed names is exempt from both checks by default, so a repo never has to list them. The set is `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `LICENSE`, `CODEOWNERS`, `CLAUDE.md`, and `AGENTS.md`, matched case-sensitively on the basename.

`filename-extensions` replaces the default mapping wholesale rather than merging into it, so repeat `.yml = ".yaml"` alongside any extra entries, or declare the table empty to disable the extension check. `filename-case` and `filename-ignore` apply to the extension check and the casing check alike. `filename-ignore` globs use `fnmatch` semantics against the repo-relative path, and extend the built-in exempt set for any further fixed name a tool mandates.

Both checks skip `.py` files, whose names are already governed by import-identifier conventions. RS033 also only ever sees a file the invocation discovers: a bare directory argument and the shipped hook both limit discovery to `.py`, `.toml`, `.yaml`, `.yml`, and `.md`. An extensionless name such as `Dockerfile` reaches the rule only if the repo widens its hook's `types` and `files`, or names the file as an explicit CLI argument.

### Imperative verbs (RS034)

RS034 matches a fixed, curated verb list adapted from pydocstyle's own word list, plus a few gradienthealth-specific exclusions. A repo whose domain disagrees tunes the list:

```toml
[tool.repostyle]
imperative-verbs-extra = ["Deploy"]  # a verb this repo's docstrings use imperatively
imperative-verbs-exclude = ["Cache"] # a verb whose noun reading dominates here
```

`imperative-verbs-extra` adds to the shipped list rather than replacing it, and `imperative-verbs-exclude` removes from the combined result. Neither key needs the other.

### The public surface (RS029)

RS029 flags a module-level name used only inside its own module. A repo declares its public surface so the rule does not flag it. A name is left alone when it appears in any `__all__`, is re-exported from a package `__init__.py`, or is a `[project.scripts]` entry point. Three keys cover what those cannot reach:

```toml
[tool.repostyle]
public-names = ["handler"]        # names always treated as public API
public-modules = ["src/*/api.py"] # further modules that count as re-export surfaces
public-decorators = ["fixture"]   # a decorator that publishes what it wraps
```

`public-modules` globs are repo-relative and use `fnmatch` semantics, matching the way the `exclude` globs do. `public-decorators` matches a decorator's final attribute name, so the entry `fixture` covers both `@fixture` and `@pytest.fixture`.

## Suppress a finding

To waive a single finding without disabling the rule repo-wide, add an inline directive:

- `# style: ignore[RS010]` drops the named rule on that line. Comma-separate to list several: `# style: ignore[RS001, RS011]`.
- `# style: ignore-block[RS010]` drops the named rule across a whole block: a class, a function, or any multi-line statement in Python, and a folded (`>`) scalar in YAML.
- `# style: ignore-file[RS010]` drops the named rule everywhere in the file, and can sit anywhere in it.

Each of the three drops every rule's findings in its scope when written without the bracket. The `style` token, rather than ruff's `noqa`, keeps these from colliding with ruff's own suppression handling.

A block directive attaches to the first block starting on or after its own line, so write it either above the block or trailing the block's opening line. The span it covers runs from the statement's first decorator to its last body line, which is how one directive silences a class along with its methods:

```python
# style: ignore-block[RS011]
@dataclass
class ImportManager:  # the class and every method below are covered
    def load(self) -> None: ...


class Other:
    def parse(self) -> None:  # style: ignore-block[RS012]
        ...                   # only this method is covered
```

In YAML the block is a folded scalar, so one directive covers the prose RS009 reads from it:

```yaml
description: >-  # style: ignore-block[RS009]
  Every line of this scalar is covered, and only this scalar.
```

Where nothing follows a block directive, it covers its own line alone. So does one in a file with no Python tree to attach to: a TOML, YAML, or shell file, or a Python file that does not parse.

## Fix findings in place

Run with `--fix` to rewrite the mechanically-fixable findings instead of only reporting them:

```bash
repostyle --fix $(git diff --name-only)
```

Eight rules are fixable:

| Rule | What `--fix` does |
| -- | -- |
| RS005 | Rewrites a double-backtick code span to single backticks. |
| RS009 | Refills the paragraph at its own hanging indent. |
| RS030 | Adds the missing terminal punctuation. |
| RS049 | Recases the acronym. |
| RS050 | Rewrites the Google Cloud term to its current form. |
| RS054 | Rewrites the dash to the spaced `--`. |
| RS058 | Rewrites the alias section header to its canonical spelling. |
| RS061 | Collapses the double space after sentence-ending punctuation. |

The RS009 fixer refills only paragraphs the check flagged, and leaves prose the rule accepts alone. It never touches a verbatim structure such as a code fence, doctest, table, rule, or section header. It never touches a preformatted line either, meaning one ending in a `\` continuation or holding an interior run of spaces that aligns a column. It respects `# style: ignore` directives.

In YAML, RS009 also reads the prose inside a folded (`>`) block scalar. A folded scalar's single line breaks fold to spaces, so rewrapping its lines leaves the value it holds unchanged. A literal (`|`) scalar is never touched, since its breaks are content. A folded scalar counts as prose only when it closes on a `.`, `!`, or `?`, which keeps the rule off the `>` blocks that merely wrap a long expression such as a Cloud Workflows interpolation or an IAM condition. A folded scalar that closes on anything else goes unchecked, and no other rule covers it either -- RS030 reads `#` comments alone, and it cannot be extended here, because the punctuation it looks for is the same signal that tells prose from an expression. End the prose with a period and both rules apply. A line indented past the scalar's own indent ends the paragraph rather than joining it, since folding keeps the break before such a line.

A comment fixer reaches every language its check reads, so a `#` comment is repaired in TOML, YAML, and shell as well as Python. A docstring fixer acts on Python alone.

`--fix` exits non-zero when it changed a file, so a pre-commit run stops and you re-stage the rewritten files.

## Explain a rule

A finding's one-line message says what tripped. The `explain` subcommand says how to fix it and how to generalize the fix to lines the linter did not flag. It prints a card with the rule's contract, its rationale, before-and-after examples, and any reference table:

```bash
repostyle explain RS010 # one rule
repostyle explain --all # every rule's card
```

A finding from a rule that carries a card prints a one-line pointer to stderr:

```
→ run 'repostyle explain RS010' for guidance and examples
```

An agent reading the failure stream can then pull the detail on demand, at no token cost until it asks. Pass `--no-explain-hint` to suppress the pointer. Rules whose one-line message already implies the fix are left at their summary, so the cards that exist stay worth reading.

## Scope findings to changed lines

`--diff` is deprecated and will be removed in a later release. Line scoping was standing in for grandfathering, which the [baseline](#grandfather-the-existing-backlog) now does by record, and does without hiding a finding on a line the change did not touch. A run that passes `--diff` says so on stderr.

It still works meanwhile, reporting only findings on lines the change touched:

```bash
repostyle --diff $(git diff --name-only origin/main)
```

`--diff` intersects each finding's line with the lines that differ from `--diff-base`. That base defaults to the merge-base of `HEAD` and the repo's default branch, which is the commit a pull request branched from. The scope is therefore the same at a local commit and under a CI pass over a checked-out branch, so one hook entry covers both. Name a ref explicitly to compare against something else.

The intersection is on the finding's own line, so a whole-unit finding — a complexity rule reported at the `def` — re-arms only when that line itself changes. A finding on an untracked file, or one that cannot be diffed, is reported in full so nothing is hidden by accident.

`--diff` needs the base commit in the checkout, so CI has to fetch it:

```yaml
steps:
  - uses: actions/checkout@v4
    with:
      fetch-depth: 0 # --diff needs the base commit
```

Without it no base resolves and the run exits 2 saying so, rather than reporting the whole tree. Under the error-by-default severity that would fail the build on the entire grandfathered backlog, which reads as a linter outage rather than the misconfiguration it is.

This scopes repostyle's own rules only. Ruff has no diff mode, so to scope the ruff rules to a pull request's lines, filter ruff's output in CI with [reviewdog](https://github.com/reviewdog/reviewdog) (`-filter-mode=added`), or use graylint locally.

## Extend the base ruff config

`ruff-base.toml` is the shared baseline: line length 88, double-quote formatting, the `select` and `ignore` set, Google pydocstyle, banned relative imports, and 88-column doc lines. Extend it from the consuming repo's `pyproject.toml`:

```toml
[tool.ruff]
extend = "path/to/ruff-base.toml"
target-version = "py311"
```

Override only repo-specific knobs, such as the target version and per-file ignores, on top of the inherited baseline.

## Distribute the lint gate suite

Beyond the linter, this repo distributes the third-party quality gates the house style runs, with their versions pinned centrally. A consuming repo gets the whole suite at one pinned version instead of tracking each tool itself. The suite is bandit, vulture, deptry, interrogate, and codespell for Python, plus shellcheck and shfmt for shell scripts.

There are two ways to consume it, differing only in how the pinned versions reach the repo: as pre-commit hooks, which clones this repo, or as a package extra, which installs from PyPI. Neither needs credentials. Pick whichever fits how the repo already runs its linters.

### As pre-commit hooks

This repo exports a `repostyle-*` hook wrapping each gate, with the versions pinned in [`.pre-commit-hooks.yaml`](.pre-commit-hooks.yaml). A consuming repo references them all under the single `repostyle` rev, so bumping that one rev moves the whole suite.

```yaml
repos:
  - repo: https://github.com/gradienthealth/repostyle
    rev: repostyle-vX.Y.Z # pin to the latest repostyle-v release tag
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

Each Python gate reads its own `[tool.*]` table from the consuming repo's `pyproject.toml`, so the tool and its version live here while the repo-specific config stays local. A repo adopting the suite adds these tables, tuning the paths and ignore lists to its own layout:

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
# vulture flags idioms it can't see used as dead; whitelist here, extend per repo.
ignore_names = ["model_config", "exc_type", "exc_val", "exc_tb"]

[tool.deptry]
known_first_party = ["<your_package>"]

[tool.codespell]
skip = "uv.lock,*.svg,.git"
ignore-words-list = "datas,ehr,fo,hist"
```

The two shell gates configure differently, since neither tool reads `pyproject.toml`. `shellcheck` reads a `.shellcheckrc` at the repo root, so a repo tuning it commits that file — `disable=SC1091` to skip unfollowable `source` targets, for example.

`shfmt` takes flags rather than a config file. The `repostyle-shfmt` hook runs `shfmt -d -i 2 -ci`, which enforces the house default of two-space, switch-case indentation per Google's Shell Style Guide, which forbids tabs. The hook fails on any file that is not already formatted, so a consumer gets the house dialect with no per-repo config.

A repo wanting a different indent overrides through the hook's `args`, such as `args: ["-i", "4"]`, since shfmt honors the last `-i` it is given.

### As a package extra

A repo that already consumes repostyle as a package, rather than cloning this repo as a hook, installs the `gates` extra instead of referencing the `repostyle-*` hooks. The extra carries the same version pins, so the repo picks up the suite from PyPI and keeps its own `local` hooks that run each tool.

Add the extra to the dependency group the repo runs its linters from, keep the `local` hooks, and apply the same `[tool.*]` tables shown above:

```toml
[dependency-groups]
lint = [
    "repostyle[gates]>=X.Y.Z", # floor; the lockfile pins the exact version
]
```

```yaml
- repo: local
  hooks:
    - id: bandit
      name: bandit
      entry: uv run --group lint bandit -c pyproject.toml -r src
      language: system
      pass_filenames: false
      types: [python]
    # ...and one local hook per gate (vulture, deptry, interrogate, codespell,
    # shellcheck, shfmt), each `uv run --group lint <tool>`, so the tool
    # resolves from the extra. This path does not inherit the exported hook's
    # entry, so give shfmt the same `-i 2 -ci` the exported hook bakes in.
```

### Gates that stay consumer-side

`mypy`, `pyright`, and `pip-audit` are not exported. The first two need the consuming repo's full dependency set installed to resolve types, and `pip-audit` audits that repo's own lockfile through `uv`. All three therefore run in the repo's own environment rather than a pre-commit-isolated one.

Keep them as `local` hooks and hold their config to the same house baseline:

```yaml
- repo: local
  hooks:
    - id: mypy
      name: mypy
      entry: uv run mypy
      language: system
      types: [python]
      require_serial: true
      args: [--strict]
    - id: pyright
      name: pyright
      entry: uv run pyright
      language: system
      types: [python]
      require_serial: true
      pass_filenames: false
    - id: pip-audit
      name: pip-audit
      entry: bash -c 'uv export --format requirements-txt --no-emit-project | uv run pip-audit --disable-pip --strict -r /dev/stdin'
      language: system
      pass_filenames: false
      files: ^(uv\.lock|pyproject\.toml)$
      stages: [pre-push]
```

## Check docstrings against signatures

The base ruff config enforces docstring *style* through the `D` rules, but no ruff rule checks that a docstring's `Args`, `Returns`, and `Raises` sections match the actual signature. Add [pydoclint](https://github.com/jsh9/pydoclint) as a pre-commit hook in the consuming repo to catch that drift:

```yaml
- repo: https://github.com/jsh9/pydoclint
  rev: "" # pin to a pydoclint release tag
  hooks:
    - id: pydoclint
      args: [--style=google]
```

## The judgment layer

The `RSnnn` rules and ruff own what a tool can decide. The conventions that need a reader live in [`docs/judgment-conventions.md`](docs/judgment-conventions.md). Those cover whether a docstring is about the right subject, whether a verb means what the tree uses it to mean, and whether a test pins the contract or the implementation.

Each consuming repo's `CLAUDE.md` references that doc, so a coding agent reads the judgment conventions alongside the mechanical ones. A judgment convention that becomes mechanically decidable graduates to an `RSnnn` rule and leaves the doc, as `make_` did when it became RS025. The doc only shrinks as the linter grows.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

A rule's full definition and rationale live in its check-function docstring under `src/repostyle/rules/`. Read that before changing its behavior.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
