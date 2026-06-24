# Write-time Python principles

The shared, non-mechanical principles that should guide *writing* Python across gradienthealth repos — the judgments a linter can't make, that shape code as it's typed rather than catch it afterward. The mechanical tier lives elsewhere and is not restated here: the `RSnnn` checks in this package (RS001–RS011) and the baseline settings in `ruff-base.toml` enforce what a tool can. This file is the rest — and it leans on concrete examples, because a principle without one rarely changes what gets written.

It is deliberately general Python: no architecture, domain, tooling, or process opinions (those stay in each repo's own docs). A consuming repo references this file as always-on context — `@import`ing it from its `docs/code-style.md` — and layers its repo-specific style on top.

## Names carry meaning

Two instincts run under every naming choice: **the verb encodes cost and failure mode, the noun encodes identity** — a reader should infer "does this do I/O, can it raise, does it mutate?" from the name without opening the body — and **clarity beats brevity**: a longer name that removes a guess wins, and a name's length should scale with the scope it lives in.

- **Construction verbs say where the work happens.** `build_` is pure in-memory assembly from parts — no I/O, no persistence (`build_query`, `build_payload`). `create_` *changes the world* — writes a row, uploads an object, registers a remote resource (`create_user`, `create_bucket`). A `from_<x>` classmethod is an alternate constructor that converts one representation into an instance (`Config.from_file`), matching the stdlib idiom (`datetime.fromisoformat`). `make_` is for test fixtures (`make_user`), not production. Choosing the wrong verb lies about side effects.
- **Retrieval verbs encode cost.** `fetch_` is remote, slow, and fallible — it crosses the network and can time out or raise (`fetch_profile` over HTTP, `fetch_rows` from a database). Reserve a plain `get_` for cheap, in-memory, roughly `O(1)` access (`get_cached_token`). A caller reads the verb to decide whether the call needs a retry or a guard.
- **One verb per concept; no synonyms.** `parse_` (text or structured input to a typed object, may raise), `write_` (persist or emit), `render_` (format for output), `resolve_` (turn a reference or name into the concrete thing). A verb that asserts a condition — `validate_` / `check_` / `ensure_` — returns a verdict or raises; it never silently returns `None` to mean "fine." If you reach for `compute_` / `calculate_` / `derive_`, use whichever is already in the codebase rather than introducing its synonym.
- **Spell words out.** Prefer the full word at every scope; don't abbreviate by deleting interior letters. Short names are allowed only where the scope is tiny *and* the type is obvious: loop counters `i` / `j`, comprehension binders, recognized shorthands (`db`, `dt` for a `datetime`). Name length scales with scope — a wide-scope or public name earns descriptive length; a three-line comprehension does not. (The enforced abbreviation blacklist lives in RS010.)
- **Classes are nouns** in CapWords, named for what the object *is*, with role suffixes that say its kind (`*Client`, `*Reader`, `*Repository`, `*Settings`, `*Error`, `Fake*` for test doubles). Avoid `Manager` / `Helper` / `Util` / `Utils` — they name what a class vaguely *does* and become god-class drawers; name the responsibility instead (`ConnectionPool`, not `ConnectionManager`). A class whose best name is a verb usually wants to be a function. (Acronym casing and the discouraged suffixes are enforced by RS001 / RS011.)
- **Booleans read as a yes/no question** — prefix `is_` / `has_` / `can_` / `should_` (`is_ready`, `has_children`, `can_retry`). Keep the name positive and negate at the call site: `not is_ready` beats an `is_not_ready` that doubles up under negation. Don't compare to `True` / `False`.
- **Modules and packages are short, all-lowercase, and spelled out** (`order_parser.py`, never `cfg.py`), and a module shouldn't share the exact name of its single class. A package of peers is plural (`adapters/`); a module that is one cohesive concept is singular (`settings.py`).

## Comments and docstrings

- **Self-explanatory code over comments.** Refactor so the code explains itself — descriptive names, small single-purpose functions — before reaching for a comment. A comment earns its place only when the *why* is non-obvious: a hidden constraint, a subtle invariant, a workaround for a specific bug, behavior that would surprise a reader. Never narrate the *what*; the identifiers already say it.
- **No dangling history.** Surviving code must not reference what was removed or how it used to work (`previously we…`, `no longer needed`). That story belongs in the commit message, not in a comment the next reader has to decode.
- **Docstrings only where they earn it.** Write one for a public surface (used by other modules or as an entry point) or for genuinely complex logic. Skip the obvious private helper — an empty-calorie docstring is worse than none.
- **A docstring describes its own unit's contract, not its surroundings** — its inputs, outputs, behavior, and edge cases, not callers, neighboring functions, or deployment topology. If a sentence describes a neighbor, cut it; if it describes a constraint that shaped *this* unit, restate it from the unit's perspective. (That context belongs in a README or design doc, where it stays current as things move.)
- **Write docstrings in the imperative** (`Return the parsed record`, not `Returns…`), and include `Args` / `Returns` / `Raises` only when each carries real information — omit a section that would just echo the signature. (Imperative mood is enforced by ruff D401.)

## Composition

- **Small, single-responsibility units.** A function or class should do one thing and be nameable for that one thing without an "and." Build larger behavior by composing small units, each tested where it's defined.
- **Inject collaborators.** Pass dependencies in rather than constructing concrete ones inside the unit that uses them. A function that builds its own database client or HTTP session can't be tested without the real thing; one that accepts them takes a simple fake in a test and a real one in production.

## Test philosophy

- **Test behavior, not implementation.** Assert on observable outputs and side effects given known inputs — "given 3 records across 2 categories, the result has 3 entries," not "it called `_parse` 3 times." A test that breaks on a behavior-preserving refactor is testing the wrong thing.
- **No change detectors.** Don't assert call order or counts, and don't re-implement the production logic inside the test. For every test, answer "what bug would this catch?" — if the answer is "none," it's a maintenance cost, not a safety net.
- **Prefer injected fakes over mocks.** Mock only true external dependencies — network, storage, database, filesystem. Heavy mocking of your own internals signals a missing seam, not a testing technique; inject a fake that implements the collaborator's interface instead.
- **Test public interfaces.** Private `_helpers` get no direct tests — they're covered through the public surface that uses them. If a helper seems to need its own test, that's a sign it should be promoted to a public API.
- **Compose small tested units; test orchestrators for flow, not depth.** Test the leaf units exhaustively across their happy, edge, and error cases; test a unit that composes them only for routing — that the happy path and each failure path go where intended — since the detail is already covered beneath it.
- **One test class per unit under test, one behavior per test.** Split a test that asserts several independent things. Order tests happy path → edge → error, with related scenarios adjacent so a reader can scan by scenario.
- **Collapse input variations into table-driven (parametrized) tests** rather than near-duplicate test bodies. (Each repo keeps its own test-naming scheme.)

## File layout

**Headline first, helpers below.** The public class or function a file exists for leads; its private `_helpers` sit at the bottom. In a test module, the test cases lead and module-level helpers sit below. A reader opening a file should see what it is *for* before the supporting machinery that makes it work.
