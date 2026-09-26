# Rule reference

`repostyle` ships 66 rules. Every rule has an `RSnnn` id and a default severity. Errors describe mechanical defects; warnings identify review points or newer checks whose false-positive rate still needs observation.

Run `repostyle explain RSnnn` for a rule's full contract, rationale, examples, and references. The check-function docstring under `src/repostyle/rules/` is the canonical implementation specification.

## Naming

| Rule | Default | Check |
| -- | -- | -- |
| RS001 | error | Keep known acronyms uppercase in CapWords names. |
| RS010 | error | Spell out known abbreviations in introduced names. |
| RS011 | error | Name a class for its responsibility, not a vague role. |
| RS024 | warning | Express booleans positively instead of embedding `not` or `no`. |
| RS025 | error | Reserve `make_` for test fixtures. |
| RS026 | warning | Prefix boolean names with `is`, `has`, `can`, or `should`. |
| RS028 | error | Use `exc`, `exc2`, or a descriptive exception alias. |
| RS044 | warning | Name a boolean-returning function as a question. |
| RS051 | warning | Give Google Cloud resource-collection string parameters an `_id` suffix. |

## Documentation

| Rule | Default | Check |
| -- | -- | -- |
| RS004 | error | Document dataclass fields beside the fields, not in `Attributes:`. |
| RS018 | warning | Document a non-trivial public callable's contract. |
| RS020 | warning | Replace a definition's summary comment with a docstring. |
| RS021 | warning | Replace a dataclass field's explanatory comment with a field docstring. |
| RS023 | error | Open a docstring with the contract, not filler. |
| RS031 | warning | Put per-argument detail in `Args:`. |
| RS032 | warning | Put return-value detail in `Returns:`. |
| RS034 | warning | Open summaries descriptively, not imperatively. |
| RS041 | warning | Put exception detail in `Raises:`. |
| RS043 | warning | List exceptions that the body raises outright. |
| RS047 | warning | Capitalize Google-section entry descriptions. |
| RS056 | warning | Use only recognized Google docstring sections. |
| RS057 | warning | Keep docstring sections in canonical order. |
| RS058 | warning | Use canonical section names such as `Args:` and `Returns:`. |
| RS059 | warning | Use at most one section from each section family. |

## Prose and comments

These rules inspect docstrings and comments. Comment checks also cover TOML, YAML, and shell files unless the rule says otherwise.

| Rule | Default | Check |
| -- | -- | -- |
| RS005 | error | Use single backticks for code spans. |
| RS009 | error | Fill prose paragraphs to 79 columns. |
| RS022 | error | Format special comments as `TAG(TICKET): message`. |
| RS030 | warning | End each prose unit with terminal punctuation. |
| RS035 | warning | Keep a docstring summary within 79 columns. |
| RS036 | warning | Backtick code names referenced in docstrings. |
| RS037 | warning | End code spans on a word boundary. |
| RS038 | warning | Indent a wrapped tag comment past its tag. |
| RS039 | warning | Backtick sibling code tokens consistently. |
| RS045 | warning | Describe the present contract, not edit history. |
| RS049 | warning | Preserve canonical acronym casing in prose. |
| RS050 | warning | Use current Google Cloud product and brand names. |
| RS053 | warning | Sentence-case multi-sentence bullet items. |
| RS054 | warning | Use the spaced `--` sentence dash. |
| RS055 | warning | Replace banner comments with structure. |
| RS061 | warning | Use one space after sentence-ending punctuation. |

## Tests

| Rule | Default | Check |
| -- | -- | -- |
| RS002 | error | Name unit tests `test_StateUnderTest_ExpectedBehavior`. |
| RS003 | error | Use fakes instead of `unittest.mock` or `mock`. |
| RS013 | error | Keep a test's asserted path straight-line. |
| RS014 | error | Do not sleep in tests. |
| RS015 | warning | Review tests that construct more than three mocks. |
| RS016 | warning | Assert state, not only call choreography. |
| RS060 | warning | Do not restate literals read from one repository file. |
| RS062 | warning | Review test modules over their configured code-line limit. |
| RS063 | warning | Consolidate matching substantial helpers across test files. |
| RS064 | warning | Parametrize scalar cases that share one named contract and structure. |
| RS065 | warning | Consolidate repeated call-bearing test setup. |

## Structure and imports

| Rule | Default | Check |
| -- | -- | -- |
| RS006 | error | Keep implementation out of port modules. |
| RS012 | warning | Keep cognitive complexity at or below 15. |
| RS017 | error | Honor configured import-layer bans. |
| RS019 | warning | Order members by dependency, then alphabetically. |
| RS027 | warning | Take at most five positional parameters. |
| RS029 | warning | Make package-internal names private. |
| RS040 | warning | Name types nested deeper than two generic levels. |
| RS042 | error | Define `__eq__` and `__hash__` as a pair. |
| RS046 | warning | Iterate a sequence directly when an index adds no value. |
| RS048 | warning | Import another package through its public surface. |
| RS052 | warning | Keep an exception tuple within one failure family. |
| RS066 | warning | Review source modules over their configured code-line limit. |

## Values and files

| Rule | Default | Check |
| -- | -- | -- |
| RS007 | error | Represent module-level durations with `timedelta`. |
| RS008 | error | Do not attach tracebacks to PHI-safe logger calls. |
| RS033 | warning | Follow configured filename extension and casing conventions. |

## Scope-dependent rules

Most rules are safe in any repository. Three assume a project layout:

| Rule | Assumption | Configuration |
| -- | -- | -- |
| RS002 | Unit tests live under `tests/unit/`. | `test-naming-globs` |
| RS003 | Fakes live under `tests/fakes/`. | Leave the rule disabled if the convention does not apply. |
| RS006 | Ports live under `application/ports/`. | `port-path-globs` |

RS017 stays inert until `[tool.repostyle.banned-imports]` defines a ban.

## Severity

Under the defaults, 19 rules hard-fail and the other 47 report warnings. Those 19 are the mechanical rules:

```text
RS001 RS002 RS003 RS004 RS005 RS006 RS007 RS008 RS009 RS010
RS011 RS013 RS014 RS017 RS022 RS023 RS025 RS028 RS042
```

A warning does not fail a run unless the repository promotes it with `error` or `warnings-as-errors`. A tolerated run prints its warning count to stderr.

## Ruff overlap

RS027 mirrors ruff's preview-gated `PLR0917`. Remove RS027 when that rule becomes stable and the shared ruff base can select it without enabling preview globally.

RS042 includes ruff's preview-gated `PLW1641` and also checks the reverse case, `__hash__` without `__eq__`. When `PLW1641` becomes stable, ruff can own its half while repostyle retains the reverse check.
