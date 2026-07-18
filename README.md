# repostyle

Shared repo-style lint rules for gradienthealth repos, plus a base ruff config. The rules are a stdlib-only AST/token/line linter that catches conventions ruff does not cover; consuming repos select the subset they want and run it as a pre-commit remote hook. Most rules are Python-specific, but the comment-convention rules (RS009 wrapping, RS022 tag format, RS030 terminal punctuation, RS038 tag-comment continuation indent, RS045 temporal markers) also apply to TOML and YAML comments.

These rules are the *mechanical* half of the house style. The *judgment* half — conventions a linter cannot decide — lives in [`docs/judgment-conventions.md`](docs/judgment-conventions.md), the canonical source each repo references and the `python-style-review` skill distills.

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
| RS009 | Doc fill: docstring and comment paragraphs must fill to 79 columns. Docstrings are checked in Python; comments in Python, TOML, and YAML. |
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
| RS020 | Summary comment as docstring (warning): a module, class, or function with no docstring whose first body position is a standalone prose comment should carry that summary as a docstring, where this package's own docstring-content rules can see it. |
| RS021 | Field comment as docstring (warning): a `@dataclass` field documented with a trailing prose comment and no following string-literal docstring should use the per-field docstring the house style prefers. |
| RS022 | Comment-tag format: a special comment must read `TAG(TICKET): message` with an allowed tag (`TODO`, `FIXME`, `NOTE`, `HACK`) and a ticket matching a configured pattern (see below). |
| RS023 | Filler docstring opening: a docstring whose summary opens with `This function`, `This method`, `This class`, `This module`, `Helper to`, `Helper for`, `Used to`, `Simply`, or `Just` restates the identifier instead of stating the contract. |
| RS024 | No negated boolean (warning): a boolean name (prefixed `is`, `has`, `can`, or `should`) may not embed `not` or `no` as a word; name the positive and negate at the call site (`is_fresh`, not `is_not_stale`). |
| RS025 | No make in production: a `make_` function is reserved for test fixtures; outside a test module (or `conftest.py`) use `build_` for in-memory assembly or `create_` for a side effect. |
| RS026 | Boolean prefix required (warning): a `bool`-annotated parameter, variable, or attribute should read as a yes/no question — prefix it with `is`, `has`, `can`, or `should` (`is_valid`, not `valid`). A `-> bool` function is left alone, since a predicate verb is the idiomatic name for one. |
| RS027 | Too many positional arguments (warning): a definition with more than five positional parameters is flagged; make the extra ones keyword-only after a `*`. Counts positional-only and positional-or-keyword parameters, excludes a method's `self`/`cls`, and never counts keyword-only ones — so a keyword-only DI builder is left alone. A stand-in for ruff's preview-gated `PLR0917`; see below. |
| RS028 | Exception alias: an `except ... as` name must be `exc`, `exc` plus digits (`exc2`) for a nested handler, or a descriptive name of at least four characters; the noise aliases `e`, `ex`, and `err` are rejected. |
| RS029 | Should be private (warning): a module-level name used only within its own module should be prefixed `_` to mark it internal, or added to `__all__` if it is part of the public API. |
| RS030 | Terminal punctuation (warning): a docstring or comment prose unit must end with `.`, `!`, or `?` (per PEP 257); a single-line comment fragment must not. Comments are checked in Python, TOML, and YAML. |
| RS031 | Arg described in prose (warning): per-argument detail narrated in the docstring body belongs in an `Args:` section. |
| RS032 | Return described in prose (warning): the return value narrated in the docstring body belongs in a `Returns:` section. |
| RS033 | Filename convention (warning): a non-Python file's extension and casing follow the configured preference, defaulting to `.yaml` over `.yml` and kebab-case for a multi-word name (see below). |
| RS034 | Imperative docstring opening (warning): a docstring summary opens with a known bare-infinitive verb (`Return`, `Build`, `Fetch`, ...) instead of its descriptive third-person conjugation (`Returns`, `Builds`, `Fetches`, ...); the verb set is config-tunable (see below). |
| RS035 | Doc summary overflow (warning): a docstring summary line — the whole line of a single-line docstring, or the opening line of a multi-line one — runs past 79 columns; unlike a body paragraph it has no second line to reflow onto, so it must be shortened by hand. |
| RS036 | Unbackticked code reference (warning): a docstring names a code identifier the module itself binds — a parameter, import, function, class, or accessed attribute — or a literal `None`/`True`/`False` without wrapping it in single backticks. To stay mechanical it fires only where the token's shape rules out an English word (an underscore, an interior capital, a digit, or a mid-sentence leading capital), so a lowercase name that doubles as English (a `path` parameter) and a domain acronym the code does not bind (`TOML`, `FHIR`) both pass, left to review. |
| RS037 | Glued code span (warning): a code span in docstring, comment, or markdown prose ends on a word boundary. A possessive, plural, or verb suffix run straight onto the closing backtick reads as part of the identifier and breaks the span in rendered Markdown, so the suffix moves outside the span. A hyphenated compound such as `-typed` or `-safe` is left alone, since it still ends the span on a word boundary. |
| RS038 | Tag-comment continuation indent (warning): a tag comment (`TODO(TICKET): ...`) that wraps onto a further line indents its continuation past the tag, so the wrapped text reads as one unit. A contiguous run of `#` comments at one column is the unit, so an unrelated note is set off by a blank line rather than folded into the tag; a follow-on line that is itself a tag comment is a new tag and is left alone. Checked in Python, TOML, and YAML. |
| RS039 | Unbackticked sibling symbol (warning): where a docstring or comment block already backticks one code symbol, a bare sibling token in the same block stays bare. To keep the false-positive rate near zero it fires only past two guards — the block must already backtick a code-shaped token, and the bare token must recur verbatim inside a string literal in the same file (a table or column name in an embedded SQL statement, say) as self-contained proof it names a real identifier. A name the module binds is left to RS036, so the two never flag one token. Only Python is scanned, since the string-literal proof is read from the file's own AST. |
| RS040 | Deeply-nested type (warning): a type annotation nests subscripted generics past two levels (`list[tuple[str, list[int]]]`, `dict[str, tuple[Callable[..., None], ...]]`), which usually stands in for a type that wants a name; extract a `TypeAlias`, `NamedTuple`, or dataclass rather than reformat. Every `ast.Subscript` layer counts the same, `tuple` and `Callable` included, so a two-level `Iterator[tuple[...]]` idiom passes but a third nested subscript does not. Covers a parameter, return, variable, or `TypeAlias` annotation. |
| RS041 | Raise described in prose (warning): an exception narrated as raised in the docstring body belongs in a `Raises:` entry. Anchors on a backticked `*Error`/`*Exception` name sharing a sentence with a non-negated raise verb (`raises`, `re-raises`, `propagates`, and their tenses), so it also catches an exception that propagates from a callee with no `raise` statement in the function itself — the case an AST-based `Raises:` checker cannot see. |
| RS042 | Eq/hash pairing: a class that defines `__eq__` without `__hash__` (Python then sets `__hash__` to `None`, making instances unhashable) or `__hash__` without `__eq__` is flagged; define both or neither. A `@dataclass`/`attrs` class, a class inheriting the missing half from a non-`object` base, and a class explicitly setting `__hash__ = None` are exempt. A stand-in for ruff's preview-gated `PLW1641`; see below. |
| RS043 | Raises section incomplete (warning): a function that already has a `Raises:` section but raises a specific exception type outright (an explicit `raise SomeError(...)`) that the section omits. Fires only when a `Raises:` section is present — whether to document exceptions at all is RS041's prose-side concern — and yields to RS041 for any exception the body prose already narrates, so the two never double-flag one exception. |
| RS044 | Predicate function naming (warning): a `-> bool` function named as a single bare state word (`valid`, `ready`, `enabled`) should read as the yes/no question its call site asks (`is_valid`). Deliberately narrow to keep false positives near zero: it fires only on a single-word name, since a multi-word name already carries a predicate (`field_has_docstring`), and it accepts a third-person verb (`matches`, `suppresses`). A dunder, a property setter, and an `@override`/`@overload` are exempt. |
| RS045 | Temporal marker (warning): a docstring or comment that narrates the edit instead of the code — one of a tight set of temporal / diff-narrative markers (`previously`, `used to`, `formerly`, `originally`, `as discussed`, `we decided`, `for now`, `changed to`, `switched to`) — belongs in the commit message, not durable prose. Matched case-insensitively on a word boundary over docstrings and `#` comments (Python, TOML, YAML); a marker quoted in a backtick span is read as data and left alone. The set is kept tight on purpose (ambiguous words like `currently`, `instead of`, `note that` are left to the `common-style-review` prose-economy lens this rule is the floor under). Not auto-fixable — cutting narration cleanly needs judgment. |
| RS046 | Range-len re-index (warning): a `for i in range(len(seq))` loop that uses the index only to subscript that same sequence (`seq[i]`) should iterate `seq` directly (`for item in seq:`). Scoped tightly to keep false positives near zero — it fires only when every use of the index is an `seq[i]` subscript of the one sequence (a plain name or an attribute like `self.rows`), so an index also needed for arithmetic, a second sequence, or a call leaves the loop alone rather than reaching for the weaker `enumerate` suggestion this rule does not make. Covers `for` and `async for`. No stable ruff rule expresses this — pylint's `C0200` is not ported to ruff's set — so it is a genuine gap. |
| RS047 | Lowercase entry description (warning): an `Args:`/`Returns:`/`Raises:`/`Yields:` entry description opens with a capital letter (`bar: A bar.`, `NotFoundError: If a foo is not found.`), the opening-capital complement to RS030's closing period — the house treats each entry description as a full sentence. Fires only on a lowercase ASCII prose letter; a description opening with a backtick code span, an inherently-lowercase code token (a parameter name or a dotted path like `json.dumps`), a digit, or any other non-letter is left alone, and an empty description is skipped. ChromiumOS's Python style guide requires capitalized full-sentence argument descriptions and Google's own `Args:` examples are capitalized, yet no ruff or pydocstyle rule enforces it — a genuine gap. |
| RS048 | Private import (warning): a first-party import that reaches a leading-underscore module or name (`from myapp.core._engine import run`) from outside the package that owns it should go through the package's public `__init__` surface instead (`from myapp.core import run`). A single leading underscore marks a member internal to its package, so reaching it from elsewhere relies on an implementation detail; if it is needed outside, it should be lifted onto the re-export surface rather than reached past. The enforcement dual of RS029 — RS029 asks a package to hide what only it uses, RS048 asks other code not to reach into what was hidden. Scoped to imports sharing the importer's top-level package, so it governs a repo's own layering and leaves a reach into a third-party distribution (whose internals a repo cannot restructure) and a test module (where exercising internals is expected) alone. Follows PEP 8's *Public and internal interfaces*. |

### Repo-agnostic vs repo-specific

Most rules are repo-agnostic and safe to enable anywhere. Two are tied to the fhir-ingestor hexagonal architecture and its test conventions, and other repos (for example a Beam monorepo) should NOT select them:

- **RS002** assumes PascalCase test naming under `tests/unit/`. Repos with a different test-naming convention should not select it.
- **RS006** bans concrete implementation libraries inside a `src/fhir_ingestor/application/ports/` path. The path fragment and the hexagonal `ports` layering are fhir-ingestor-specific.

RS003 (mock ban) is also somewhat opinionated, since it presumes a `tests/fakes/` directory; enable it only where that convention holds. Every other rule (RS001, RS004, RS005, and RS007 through RS048) is a general style rule, repo-agnostic and safe to enable anywhere; the paragraphs below note which of them warn rather than hard-fail.

The test-quality rules (RS013–RS016) apply only to `test`-prefixed functions in test files, so they are inert elsewhere. RS012, RS015, RS016, RS018, RS019, RS020, and RS021 are advisory: they emit a `warning` and do not fail the run, since their signals are heuristics that mark where to look rather than assert a defect. RS027 warns too, matching how the repo's other threshold rule (RS012) is treated; note that ruff's `PLR0917`, which it stands in for, is a hard error, so adopting it later raises the severity. The boolean-naming rules RS024 and RS026 are advisory too, warning rather than failing until their false-positive rate on the existing repos is measured. RS033 is advisory too: its casing default is an industry-wide convention, not a Gradient-measured one, and a repo's existing files may need a batch of `filename-ignore` entries before it is worth hard-failing. RS034 is advisory too: it matches only a fixed, curated verb list, so it neither catches every imperative opening nor is guaranteed free of a false match on an unmeasured repo. RS035 is advisory too, since its fix is "shorten this by hand" rather than a mechanical rewrite. RS036 is advisory too: it deliberately under-flags, matching only code-shaped names to keep its false-positive rate near zero, so the lowercase references it skips are left to review. RS037 is advisory too: the possessive and verb-suffix cases are crisp, but the plural case is mildly contestable, so it warns rather than failing until its false-positive rate on the existing repos is measured. RS038 is advisory too, since folding a note into a preceding tag comment versus starting a fresh one is a mild layout call, so it warns until its false-positive rate on the existing repos is measured. RS039 is advisory by design and stays that way: its consistency gate and string-literal evidence mark where a bare sibling most likely belongs in backticks rather than asserting a defect, so it warns rather than failing. RS040 is advisory too: its nesting-depth limit is a heuristic threshold that marks a type worth a second look rather than asserting a defect. RS043 is advisory too, since a present-but-incomplete `Raises:` section is a documentation-drift smell rather than a code defect. RS044 is advisory too: its single-bare-word heuristic marks a name to reconsider rather than asserting one is wrong. RS045 is advisory too: its marker set is a high-precision floor, and it is deliberately not auto-fixable, since cutting the narration cleanly is a judgment call left to review. RS046 is advisory too: rewriting a re-index loop to direct iteration is a mechanical enough call, but it stays a warning until its false-positive rate on the existing repos is measured. RS047 is advisory too, matching RS030 (its closing-period complement): it warns until its false-positive rate on the existing repos is measured. RS048 is advisory too: importing a package's internals from outside it is an encapsulation smell rather than a hard defect, and it stays a warning until its false-positive rate on the existing repos is measured. RS013, RS014, RS022, RS023, RS025, RS028, and RS042 are mechanical and hard-fail. The documentation-form rules (RS020, RS021, and RS023) are general style rules. A repo that trusts a given advisory rule on its own codebase can promote it to a hard failure with the `[tool.repostyle] error` key (see below), gating on that subset without disturbing the rest.

RS027 is a stand-in for ruff's [`PLR0917`](https://docs.astral.sh/ruff/rules/too-many-positional-arguments/) (`too-many-positional-arguments`), which is preview-gated in the pinned ruff version. Enabling it through ruff would require setting `preview = true` on the shared `ruff-base.toml`, a global switch that turns on preview behavior for every rule and the formatter across all consuming repos, so the rule lives here instead. It mirrors `PLR0917`: the default cap of five, the positional-only counting, the `self`/`cls` exclusion, and the `@override` exemption. When `PLR0917` graduates to stable in the pinned ruff version, select it in `ruff-base.toml` and delete RS027 (PROC-2319).

RS042's eq-without-hash half is a stand-in for ruff's [`PLW1641`](https://docs.astral.sh/ruff/rules/eq-without-hash/) (`eq-without-hash`), preview-gated in the pinned ruff version the same way `PLR0917` is, so selecting it would require the global `preview = true` switch. RS042 goes further than `PLW1641`, which only flags the eq-without-hash direction, by also flagging `__hash__` without `__eq__`. When `PLW1641` graduates to stable, select it in `ruff-base.toml` and drop RS042's eq-without-hash half, keeping the hash-without-eq half here.

## Consume as a pre-commit remote hook

Add to the consuming repo's `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/gradienthealth/repostyle
    rev: repostyle-vX.Y.Z  # pin to the latest repostyle-v release tag
    hooks:
      - id: repostyle
```

The hook runs the `repostyle` console script over the staged Python, markdown, TOML, and YAML files. Most rules act on Python only; the comment-convention rules (RS009, RS022, RS030, RS045) also act on TOML and YAML comments.

## Select rules per repo

The runner reads the consuming repo's `pyproject.toml`:

```toml
[tool.repostyle]
select = ["RS001", "RS004", "RS005", "RS007", "RS008", "RS009", "RS010", "RS011"]
ignore = []
error = ["RS034", "RS035"]  # promote these advisory rules to hard-fail
```

Enabled rules are `select` minus `ignore`. If the table is missing or empty, all rules are enabled. The nearest `pyproject.toml` is discovered by walking up from the first target path's directory.

`error` promotes chosen advisory (warning-severity) rules to error severity, so a finding from one prints as an error and fails the run, exactly as a natively-error rule does. It is the surgical alternative to a blunt "fail on all warnings" switch: a repo gates on a trusted subset while leaving the false-positive-prone heuristic rules advisory. A promoted rule that is disabled never fires, so its promotion is inert; promoting a rule that is already error by default is a harmless no-op. An unknown id in `error` is rejected the same way `select`/`ignore` validate their ids.

## Exclude paths from scanning

`exclude` drops a file from linting entirely — every rule, no findings — so generated or vendored code stays out of the scan without an editor integration or a bare `repostyle .` re-flagging it:

```toml
[tool.repostyle]
exclude = ["*_pb2.py", "*_pb2_grpc.py", "vendor/*"]  # globs skipped by every rule
```

The globs use the same `fnmatch` semantics and repo-relative matching as `filename-ignore` (matched against the path relative to the discovered `pyproject.toml`). In `fnmatch`, `*` spans `/`, so a name glob like `*_pb2.py` matches at any depth and there is no recursive `**` operator — to exclude a `_grpc` directory wherever it sits, write `*_grpc/*.py`, not `**/_grpc/*.py`. A match is dropped however it reaches repostyle: whether walked from a directory argument or passed explicitly, so a regenerated file the pre-commit hook passes by name is skipped too. With no `exclude` configured, every discovered file is scanned. This is a global discovery filter, distinct from `filename-ignore`, which only exempts a file from the RS033 filename-convention rule while leaving every other rule to scan it.

## Skip gitignored trees (`respect-gitignore`)

A repo already lists its vendored and generated trees in `.gitignore`. Rather than restate each in `exclude`, set `respect-gitignore` and repostyle prunes a directory the repo's root `.gitignore` names — the `.gitignore` beside the discovered `pyproject.toml`:

```toml
[tool.repostyle]
respect-gitignore = true  # prune directories the root .gitignore names
```

The flag is off by default, so no existing repo's behavior changes and a repo that gitignores a path it does want linted is not surprised. Built-in structural pruning (a dot-directory, `venv`, `node_modules`, and build outputs) applies regardless of this flag.

A gitignored path is treated as not part of the repo at all: a pruned directory is invisible to every rule, including the RS029 whole-package visibility index. This is the deliberate split from `exclude`, which keeps a file in the tree and only silences its findings — a generated stub kept in the tree by `exclude` still counts as a cross-module reference for RS029, a gitignored one does not.

The matcher honors a small, well-defined subset of `.gitignore` syntax, enough for the vendored-tree case: blank lines and `#` comments are skipped; a trailing-slash `foo/` and a bare `foo` both name a directory; a leading-slash `/foo` or an internal-slash `foo/bar` anchors to the repo root, while a bare name matches a directory so named at any depth. Glob matching is `fnmatch`, as the `exclude` globs already use, so `*` spans `/`. Two constructs are deliberately not supported: a `!` negation is never honored as a re-inclusion (an anchored one only spares its own subtree from pruning; an unanchored one, whose any-depth reach cannot be bounded cheaply, switches gitignore pruning off for the whole repo rather than risk mis-pruning a re-included path), and per-directory nested `.gitignore` files below the root are not read. When either bound would matter, keep using `exclude`, which is unaffected.

## Configure the acronym list (RS001)

RS001 checks a fixed set of acronyms (`API`, `FHIR`, `HTTP`, `ID`, `JWT`, `URL`, ...) for uppercase casing in CapWords names. A repo whose domain carries its own acronyms tunes the set without a repostyle source change:

```toml
[tool.repostyle]
acronyms-extra = ["UID", "SCU", "SCP", "PACS"]  # domain acronyms this repo's names use
acronyms-exclude = ["DOB"]                      # a shipped acronym too aggressive for this repo
```

`acronyms-extra` adds to the shipped set rather than replacing it; `acronyms-exclude` removes from the combined result, so it can drop a shipped acronym, an added one, or both. Entries are matched uppercased, so their case here does not matter. Neither key needs the other configured.

## Configure layering bans (RS017)

RS017 takes its bans from config, so each repo expresses its own layering. Map a path glob (relative to the repo root, `fnmatch` semantics) to the import sources files under it may not import:

```toml
[tool.repostyle.banned-imports]
"src/**" = ["tests"]
"**/application/ports/**" = ["httpx", "sqlalchemy", "psycopg", "boto3", "google.cloud.bigquery"]
```

A file matching a glob that imports a banned source — or a submodule of it (`tests.fakes`) — is flagged. Relative imports are left to the no-relative-imports ruff rule. With no table, RS017 reports nothing, so selecting it is harmless until a layer is configured.

## Configure comment tags (RS022)

RS022 holds a special comment to `TAG(TICKET): message`. The allowed tag set and the ticket pattern are config-driven, so a repo expresses its own ticket shape; both fall back to a default when omitted:

```toml
[tool.repostyle]
comment-tags = ["TODO", "FIXME", "NOTE", "HACK"]
comment-ticket-pattern = "[A-Z]+-\\d+|NO-ISSUE"
```

A comment whose leading token is an allowed tag, or a known alias of one (`XXX`, `BUG`, `TBD`, ...), is held to the canonical form; the alias steers toward the first allowed tag. A deviation — an unknown tag, wrong casing, a missing or malformed ticket, or a wrong separator — is flagged. A comment whose leading token is neither a tag nor an alias is ordinary prose and is left alone. The default ticket pattern is the Linear-id shape plus the literal `NO-ISSUE`.

## Configure filename conventions (RS033)

RS033 checks a non-Python file's extension and casing, and ships a default for both rather than reporting nothing until configured — `.yaml` over `.yml` (yaml.org's recommended extension since 2006) and kebab-case for a multi-word name (Google's developer documentation style guide, since a search engine reads a hyphen as a word break but not an underscore):

```toml
[tool.repostyle]
filename-case = "kebab"                        # or "snake", or "none" to disable
filename-ignore = [".github/workflows/*.yml"]  # globs exempted from both checks

[tool.repostyle.filename-extensions]
".yml" = ".yaml"
```

A curated set of fixed names whose spelling a tool or ecosystem convention mandates — `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `LICENSE`, `CODEOWNERS`, `CLAUDE.md`, `AGENTS.md` — is exempt from both checks by default (matched case-sensitively on the basename), so a repo never has to re-list them. `filename-extensions` replaces the default mapping wholesale rather than merging into it — repeat `.yml = .yaml` alongside any extra entries, or declare the table empty to disable the check. `filename-case` and `filename-ignore` apply to both the extension and the casing check. `filename-ignore` globs (`fnmatch` semantics, matched against the path relative to the repo root) extend the built-in exempt set for any further fixed name a tool or convention mandates — `.github/workflows/*.yml` if the repo keeps GitHub Actions' own `.yml` convention — rather than renaming them. Both checks skip `.py` files, whose names are already governed by import-identifier conventions.

RS033 only ever sees a file its invocation actually discovers: a bare directory argument and the shipped `repostyle` pre-commit hook both limit discovery to `.py`/`.toml`/`.yaml`/`.yml`/`.md`. An extensionless fixed name like `Dockerfile` or `LICENSE` only reaches the rule if the consuming repo widens its own hook's `types`/`files` to pass it, or names it as an explicit CLI argument.

## Configure the imperative-verb list (RS034)

RS034 matches a fixed, curated verb list, adapted from pydocstyle's own word list plus a handful of gradienthealth-specific exclusions. A repo whose own domain disagrees tunes the list without a repostyle source change:

```toml
[tool.repostyle]
imperative-verbs-extra = ["Deploy"]      # a verb this repo's own docstrings use imperatively
imperative-verbs-exclude = ["Cache"]     # a verb whose noun reading dominates in this repo's domain
```

`imperative-verbs-extra` adds to the shipped list rather than replacing it; `imperative-verbs-exclude` removes from the combined result, so it can drop a shipped verb, an added one, or both. Neither key needs the other configured.

## Suppress a finding

To waive a single finding without disabling the rule repo-wide, add an inline directive:

- `# style: ignore[RS010]` — drop the named rule on that line (comma-separate to list several: `# style: ignore[RS001, RS011]`).
- `# style: ignore` — drop every rule's findings on that line.
- `# style: ignore-file` — drop every finding in the file; place it anywhere in the file.

The `style` token, rather than ruff's `noqa`, keeps these from colliding with ruff's own suppression handling.

## Scope findings to changed lines

Adopting a rule should not mean fixing the whole existing codebase first. Run with `--diff` to report only findings on lines the change touched:

```bash
repostyle --diff --diff-base origin/main $(git diff --name-only origin/main)
```

`--diff` intersects each finding's line with the lines that differ from `--diff-base` (default `HEAD`); a finding on an untracked file or one that cannot be diffed is reported in full, so nothing is hidden by accident. The intersection is on the finding's own line, so a whole-unit finding (a complexity rule reported at the `def`) re-arms only when that line itself changes.

This scopes repostyle's own `RSnnn` rules. Ruff has no diff mode, so to scope the ruff rules to a PR's lines, filter ruff's output in CI with [reviewdog](https://github.com/reviewdog/reviewdog) (`-filter-mode=added`) or graylint locally.

## Rewrap docstrings and comments

`RS009` flags docstring and comment paragraphs that are not filled to 79 columns. Run with `--fix` to rewrite the mechanically-fixable findings in place instead of only reporting:

```bash
repostyle --fix $(git diff --name-only)
```

`--fix` rewrites the fixable rules — `RS009` reflow, `RS005` double-to-single backticks, and `RS030` terminal punctuation (`_registry.FIXABLE_RULES`). For `RS009` it greedily refills each paragraph at its hanging indent, leaving verbatim structures (code fences, doctests, tables, rules, section headers) untouched and respecting `# style: ignore` directives. It exits non-zero when it changed a file, so a pre-commit run stops and you re-stage the rewritten files.

## Explain a rule

The one-line finding says what tripped; the `explain` subcommand says how to fix it and how to generalize the fix to lines the linter did not flag — a card with the rule's contract, rationale, before/after examples, and any reference table:

```bash
repostyle explain RS010      # one rule
repostyle explain --all      # every rule's card
```

A finding from a rule that carries such a card prints a one-line pointer to stderr (`→ run 'repostyle explain RS010' for guidance and examples`), so an agent reading the failure stream pulls the detail on demand at no token cost until it asks. Pass `--no-explain-hint` to suppress the pointer. The card is the same data for every rule; the rules whose one-line message already implies the fix are left at their summary, so the cards stay worth reading.

## Extend the base ruff config

`ruff-base.toml` is the shared baseline (line length 88, double-quote format, the `select`/`ignore` set, Google pydocstyle, banned relative imports, 88-column doc lines). Extend it from the consuming repo's `pyproject.toml`:

```toml
[tool.ruff]
extend = "path/to/ruff-base.toml"
target-version = "py311"
```

Override only repo-specific knobs (target version, per-file ignores) on top of the inherited baseline.

## Distribute the lint gate suite

Beyond the `repostyle` linter, this repo distributes the third-party quality gates the house style runs (bandit, vulture, deptry, interrogate, codespell) with their versions pinned centrally, so a consuming repo gets the whole suite at one pinned version instead of tracking each tool itself. There are two ways to consume it, differing only in how the pinned versions reach the repo: as pre-commit hooks (clones this repo) or as a package extra (installs from the private index). Pick the one whose auth the repo already has.

### As pre-commit hooks

This repo exports `repostyle-*` hooks that wrap each gate, with the versions pinned in [`.pre-commit-hooks.yaml`](.pre-commit-hooks.yaml). A consuming repo references them under the single `repostyle` rev, so bumping that one rev moves the whole suite. Because this repo is private, pre-commit needs git-clone auth to it (a `gradienthealth-bot` token configured through `git config insteadOf` in CI); a repo without that set up should use the package extra below.

```yaml
repos:
  - repo: https://github.com/gradienthealth/repostyle
    rev: repostyle-vX.Y.Z  # pin to the latest repostyle-v release tag
    hooks:
      - id: repostyle
      - id: repostyle-bandit
      - id: repostyle-vulture
      - id: repostyle-deptry
      - id: repostyle-interrogate
      - id: repostyle-codespell
```

Each gate reads its own `[tool.*]` table from the consuming repo's `pyproject.toml`, so the tool and its version live here while the repo-specific config (exclude paths, ignore lists, layering contracts) stays local. A repo adopting the suite adds these tables, tuning the paths and ignores to its own layout:

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

### As a package extra

A repo that already consumes repostyle as a package from the private index (rather than cloning this private repo as a hook) installs the `gates` extra instead of referencing the `repostyle-*` hooks. The extra carries the same version pins, so a repo picks up the suite through the index auth it already has and keeps its own `local` hooks that run each tool. As long as the private index is declared `explicit = true` (so only repostyle is drawn from it, as in fhir-ingestor), the gate tools resolve from the default PyPI index, and the extra needs no index permission beyond the read access repostyle itself already requires.

Add the extra to the dependency group the repo runs its linters from, keep the `local` hooks, and apply the same `[tool.*]` tables shown above:

```toml
[dependency-groups]
lint = [
    "repostyle[gates]>=X.Y.Z",  # floor; the lockfile pins the exact version
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
      # ...and one local hook per gate (vulture, deptry, interrogate, codespell),
      # each `uv run --group lint <tool>`, so the tool resolves from the extra.
```

### Gates that stay consumer-side

`mypy`, `pyright`, and `pip-audit` are not exported. The first two need the consuming repo's full dependency set installed to resolve types, and `pip-audit` audits that repo's own lockfile through `uv`, so all three run in the repo's environment rather than a pre-commit-isolated one. Keep them as `local` hooks and hold their config to the same house baseline:

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

The base config enforces docstring *style* (Google convention, via the ruff `D` rules) but not that a docstring's `Args`/`Returns`/`Raises` match the actual signature — ruff's `D` rules don't check that. Add [pydoclint](https://github.com/jsh9/pydoclint) as a pre-commit hook in the consuming repo to catch that drift:

```yaml
  - repo: https://github.com/jsh9/pydoclint
    rev: ""  # pin to a pydoclint release tag
    hooks:
      - id: pydoclint
        args: [--style=google]
```

## The judgment layer

`RSnnn` rules and `ruff` own what a tool can decide. The conventions that need a reader — whether a docstring is about the right subject, whether a verb means what the tree uses it to mean, whether a test pins contract or implementation — live in [`docs/judgment-conventions.md`](docs/judgment-conventions.md). That doc is the Gradient-wide canon: each repo's `CLAUDE.md` references it, and the `python-style-review` skill distills it into its review lenses. A judgment convention that becomes mechanically decidable graduates to an `RSnnn` rule and leaves the doc (as `make_` did to `RS025`); the doc only shrinks as the linter grows.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```
