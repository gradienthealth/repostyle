# Write-time Python principles

The shared, non-mechanical principles that should guide writing Python in gradienthealth repos — the small set of judgments a linter cannot catch. Mechanical rules live elsewhere and are not restated here: the `RSnnn` checks in this package (RS001–RS011) and the baseline ruff settings in `ruff-base.toml` cover what a tool can enforce. This file covers the rest: the calls you make as you write, before any check runs.

It is deliberately general Python — no architecture, domain, tooling, or process opinions. A consuming repo vendors this file into its `docs/shared/` and `@import`s it from `docs/code-style.md`, layering its own repo-specific style on top.

## Names carry meaning

A name is a contract. The verb encodes cost and failure mode; the noun encodes identity. Clarity beats brevity, and the length of a name should scale with the scope it lives in — a loop index can be `i`, a module-level value cannot.

- **Construction verbs say where the work happens.** `build_` is pure in-memory assembly. `create_` changes the world (writes a row, sends a request, mutates state). `from_` is a classmethod alternate constructor. `make_` is for test setup only. Picking the wrong one lies about side effects.
- **Retrieval verbs say what it costs.** `fetch_` is remote, slow, and fallible — it can time out or raise. `get_` is cheap, in-memory, and roughly `O(1)`. A caller reads the verb to decide whether the call needs a retry or a guard.
- **One verb per concept; no synonyms.** Don't scatter `validate_`, `check_`, and `ensure_` across the codebase for the same idea. A verb that asserts a condition returns a verdict or raises — it never silently returns `None` to mean "fine".
- **Classes are nouns with role suffixes.** A class whose most honest name is a verb usually wants to be a function instead.
- **Booleans read as a yes/no question:** `is_`, `has_`, `can_`, `should_`. Keep the name positive and negate at the call site; `not is_ready` beats a `not_ready` that doubles up under negation.
- **Modules are short and lowercase.** Plural for a package of peers, singular for one cohesive concept.

The enforced subset of all this — the abbreviation blacklist, the discouraged class suffixes, acronym casing — lives in the RS checker (RS010, RS011, RS001). Above is the judgment behind it, which the checker cannot fully reach.

## Comments and docstrings

- **Comments default to none.** A comment earns its place only when the *why* is non-obvious — a workaround, a surprising constraint, a decision a reader would otherwise second-guess. Never narrate the *what*; the code already says that.
- **No dangling history.** Surviving code must not reference what was removed or how it used to work. That story belongs in the commit, not in a comment the next reader has to decode.
- **Docstrings only where earned.** Write one for the public surface or for genuinely complex logic. Skip the obvious private helper — an empty-calorie docstring is worse than none.
- **A docstring describes its own unit's contract,** not its surroundings. No naming of callers, neighboring functions, or deployment topology. Include `Args`, `Returns`, and `Raises` only when each carries real information; omit a section that would just echo the signature.

## Composition

- **Small, single-responsibility units.** A function or class should do one thing and be nameable for that one thing without an "and".
- **Inject collaborators.** Pass dependencies in rather than reaching for concrete ones inside the unit. Code that constructs its own database client or HTTP session inside the function it uses them in cannot be tested without the real thing; code that accepts them can take a simple fake.

## Test philosophy

- **Test behavior, not implementation.** Assert on observable outputs and side effects given known inputs, not on how the result was produced.
- **No change detectors.** Don't assert call order or call counts, and don't re-implement the production logic inside the test. For every test, answer "what bug would this catch?" — if the answer is "none", it is a maintenance cost, not a safety net.
- **Prefer injected fakes over mocks.** Mock only true external dependencies — network, storage, database, filesystem. Heavy mocking of your own internals is a signal of a missing seam, not a testing technique.
- **Test public interfaces.** Private `_helpers` get no direct tests; they are covered through the public surface that uses them. If a helper seems to need its own test, that is a sign it should be promoted to a public API.
- **Compose small tested units.** Test the leaf units for depth; test an orchestrator for flow — that it wires the pieces together — not by re-proving each piece.
- **One test class per unit under test, one behavior per test.** Order the tests happy path, then edge, then error, with related scenarios adjacent.
- **Collapse input variations into table-driven tests** rather than near-duplicate test bodies. Each repo keeps its own test-naming scheme.

## File layout

Headline first, helpers below. The public class or function a file exists for leads; its private `_helpers` sit at the bottom. In a test module, the tests lead. A reader opening the file should see what it is *for* before the supporting machinery that makes it work.
