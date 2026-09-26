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

Shared comment extraction lives in `_comments.py`; shared configuration, parsing, and path logic lives in `_shared.py`.

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
