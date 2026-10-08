# Development

## Set up the repository

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

Run the same local checks as pre-commit:

```bash
pre-commit run --all-files
PYTHONPATH=src python3 -m repostyle.cli --no-baseline .
```

The second command bypasses the baseline and proves that the repository meets the complete current suite.

## Find the source of truth

A rule's check-function docstring under `src/repostyle/rules/` defines its contract and rationale. The package groups checks by subject. Supporting surfaces have separate owners:

| Surface | Owner |
| -- | -- |
| Rule ids and `Violation` | `rules/_violation.py` |
| Dispatch and severity | `rules/_registry.py` |
| Explanation cards | `rules/_catalog.py` |
| Public rule imports | `rules/__init__.py` |
| Configuration and file dispatch | `runner.py` |
| CLI behavior | `cli.py` |
| Baselines | `baseline.py` |
| Suppressions | `suppressions.py` |
| Changed-line compatibility | `changed_lines.py` |

`languages/` owns what repostyle knows about each language's syntax: how its comments are written, which spans a block directive covers, and where its tests live. Shared configuration and path logic lives in `_shared.py`.

## Support another language

A language reaches the rules through three layers, each owning one question:

| Layer | Owns | Example |
| -- | -- | -- |
| `languages/` | What the syntax is: comments, block spans, test layout, fill column | `_java.py` lexes Java and yields `//` comments |
| `rules/_doc_blocks.py` | How a doc comment divides into prose units | `_javadoc.py` segments Javadoc into summary, body, and tag units |
| A rule module | Whether the prose or code is good | RS034 grades every block's summary |

To add a language:

1. Register a `Language` record in `languages/_registry.py` with `is_default=False`, so only a repository that lists it under `languages` reads it.
1. Supply the hooks it has. A `comments` scanner reaches every comment rule at once.
1. If it has doc comments, segment them into `InternalProseUnit` records and add a branch to `internal_doc_blocks`, which reaches every prose rule that reads doc blocks.
1. Dogfood it against a real repository, then list the rules it reaches in a coverage section of `docs/rules.md`, as Java's section does.

A rule that inspects code rather than prose reads one language's syntax and states which language in its docstring.

## Add or change a rule

Read the existing check's docstring before changing behavior. A new rule needs each of these pieces:

1. Define the `RSnnn` id in `_violation.py`.
1. Implement the check in the subject module.
1. Register its checker and severity in `_registry.py`.
1. Re-export the public surface from `rules/__init__.py`.
1. Add its explanation metadata to `_catalog.py`.
1. Add focused behavior tests and update `docs/rules.md`.

Prefer a test that survives a behavior-preserving refactor. Use fakes instead of mock choreography, and parametrize scalar variations that exercise one contract.

## Preserve compatibility

The package is stdlib-only and supports Python 3.11 and later. Public imports from `repostyle.rules` are stable. A leading-underscore module or name is private to its package; code outside that package uses the public re-export.

Do not edit the version in `pyproject.toml`. Release Please owns it.

## Release flow

Pull requests use Conventional Commit titles with the ticket in the scope, for example `feat(PROC-123): add the rule`. Use `NO-ISSUE` when no ticket exists. The repository squash-merges, so the pull request title becomes the release input.

Merging the Release Please pull request creates the version tag, GitHub release, changelog entry, and PyPI publication. A workflow dispatch can republish the current `main` to TestPyPI or PyPI.
