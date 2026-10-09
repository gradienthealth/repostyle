# Repository guide

## Purpose

`repostyle` is a stdlib-only linter for repository conventions that ruff cannot express. It publishes the `repostyle` CLI, a pre-commit hook, `ruff-base.toml`, and optional third-party gate hooks.

The rule implementation is authoritative. Read a check function's docstring before changing its behavior; [docs/rules.md](docs/rules.md) is the user-facing index, not a second specification.

## Verify changes

Use the repository environment when one exists. The direct commands are:

```bash
PYTHONPATH=src python3 -m pytest
PYTHONPATH=src python3 -m repostyle.cli --no-baseline .
pre-commit run --all-files
```

The unbaselined repostyle run must report no warnings or errors. The repository promotes warnings to errors in `pyproject.toml`.

## Architecture

- `src/repostyle/rules/` owns checks, ids, dispatch, severities, explanation cards, and the public rule surface.
- `runner.py` resolves configuration and scans files.
- `cli.py` owns command parsing and reporting.
- `baseline.py` and `suppressions.py` filter known findings.
- `languages/` owns each language's syntax behind a `Language` record: comment scanning, the spans a block directive covers, test-file layout, and YAML folded prose.
- `_shared.py` owns shared parsing, configuration, and path behavior.
- `tests/` mirrors the behavior surfaces.
- `docs/` holds user reference and contributor guidance.

[docs/development.md](docs/development.md) maps each public surface to its owner and lists the complete rule-change checklist.

## Code conventions

- Keep internal functions and class helpers private.
- Do not introduce `Manager`, `Helper`, `Util`, or `Utils` class suffixes.
- Use descriptive Google-style docstrings in third-person present tense.
- State contracts and non-obvious invariants; omit implementation narration.
- Catch specific exceptions and keep one failure family per handler.
- Use strict type hints and absolute imports.
- Preserve public imports from `repostyle.rules`.
- Keep tests straight-line and assertion-driven. Prefer fakes over mocks.
- Parametrize scalar variations only when the cases exercise one contract.

Ruff and repostyle own mechanical style. Follow [docs/judgment-conventions.md](docs/judgment-conventions.md) for decisions that need review rather than syntax.

## Documentation ownership

- Keep the README focused on installation, first use, and navigation.
- Put rule ids and severities in `docs/rules.md`.
- Put runner options in `docs/configuration.md`.
- Put ruff and third-party gate setup in `docs/gates.md`.
- Put contributor workflows in `docs/development.md`.
- Update one owning page instead of repeating detail across several files.

`AGENTS.md` is the canonical agent guide. `CLAUDE.md` is a compatibility symlink and must continue to point here.

## Releases and Git

Do not edit the version in `pyproject.toml`; Release Please owns it. Pull request titles use Conventional Commits with a Linear ticket or `NO-ISSUE` in the scope. Never amend or force-push a shared branch.
