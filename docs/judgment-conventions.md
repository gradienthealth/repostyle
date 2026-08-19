# Judgment conventions

The judgment layer of the Python house style — the conventions a tool cannot decide, held up by review. This is the canonical source: each consuming repo's `CLAUDE.md` references it rather than restating it.

## Two layers

The house style has two layers, and they do not overlap:

- **Mechanical** — the `RSnnn` rules in this package plus `ruff`, `mypy`, and `pydoclint`. AST/token/line-decidable conventions: acronym casing, abbreviations, docstring shape, fill width, import order, member order, comment-tag format, and the naming rules that graduated here from review (a negated boolean is `RS024`, a production `make_` is `RS025`, a `bool`-annotated name missing its `is_`/`has_` prefix is `RS026`). These fail CI; an engineer never argues with them.
- **Judgment** — the conventions below. They need a reader to decide whether a docstring is about the right subject, whether a comment earns its place, whether a verb means what the tree uses it to mean. They are upheld by review, never by a linter.

A convention belongs in exactly one layer. When a judgment convention turns out to be mechanically decidable with near-zero false positives, it graduates to an `RSnnn` rule and leaves this doc — the trajectory that produced `RS024`, `RS025`, and `RS026`. What remains here is judgment that resisted that graduation.

## A. A docstring states the unit's own contract

A docstring covers what *this* unit does — its inputs, outputs, behavior, edge cases, and the errors it raises. It does not describe callers, neighboring services, deployment topology, or someone else's responsibility; that context belongs in a README or design doc, where it stays current as the topology shifts.

- A sentence describing a neighbor ("the caller then persists this to BigQuery") → cut it or move it to the neighbor.
- PR narrative or change history ("previously this returned a list, now…") → cut; that lives in the commit and PR.
- A rejected alternative ("we considered a cache but…") → cut; the docstring states the contract, not the design debate.
- A project-wide invariant the `CLAUDE.md` already owns → cut; do not duplicate it per unit.
- A constraint that genuinely shaped this unit → keep it, restated from the unit's own perspective ("rejects timestamps before the epoch", not "because downstream BigQuery cannot store them").

`RS018` flags the *presence and shape* of under-documentation; whether the prose is about the right subject is judgment.

## B. A comment justifies why, not what

A comment earns its place only for a non-obvious *why*: a hidden constraint, a subtle invariant, a bug workaround, surprising third-party behavior. The identifiers already show the *what*.

- **What-narration** restating the line below it (`# increment the counter`) → cut.
- **Absence narration** (`# no error handling needed here`, `# intentionally empty`) → cut; absence is not a comment-worthy fact.
- **Ticket references** (`PROC-1234`, `#1234`) on ordinary new code → cut; the ticket lives in the PR title and commit, and `git blame` supplies provenance. Keep one only where it carries out-of-band context the reader needs — a workaround for an incident, a flag added after an outage — or in a regression test, where it pins *why this specific behavior* is defended. (`RS022` owns the *shape* of a tag comment; whether it earns its place is judgment.)

## C. Verbs encode cost and failure mode

The verb tells a reader, without opening the body, whether a call does I/O, can raise, or mutates. A name is syntactically valid whatever verb it picks, so only judgment catches a verb that lies.

- **`build_`** — pure in-memory assembly, no I/O. A `build_` that writes a file or hits the network is mis-verbed → `create_`, or split the I/O out.
- **`create_`** — changes the world (writes, registers, calls a remote). The `create_app` / `create_*_router` web-factory idiom is the sanctioned exception: it assembles in memory despite the verb.
- **`from_<x>`** — an alternate constructor (a classmethod returning an instance), matching the stdlib (`datetime.fromisoformat`).
- **`make_`** — test fixtures only; a production `make_` is now `RS025`.
- **Retrieval is layered.** `get_` / `post_` at the transport layer mirror the HTTP verb they issue. `fetch_` is slow or fallible domain retrieval (a remote read that can fail or block). A plain `get_` elsewhere is a cheap, in-memory, roughly O(1) lookup that does not fail — a `get_` that makes a network call wants to be `fetch_`.
- **One verb per concept.** `parse_`, `write_`, `render_`, `resolve_` each name one operation; do not introduce a synonym (`compute_` / `calculate_` / `derive_`, or `load_` vs `read_` vs `fetch_`) when the tree already settled on one. Check the surrounding modules for the established verb.
- **`validate_` / `check_` / `ensure_`** return a verdict or raise — never silently return `None` on both success and failure. A predicate that swallows its result is mis-named. (This stays judgment, not a rule: whether a function signals failure can hinge on a helper it calls, which a linter cannot see.)

## D. Nouns name identity; clarity beats brevity

- **Nouns name what an object *is***, by its responsibility, not a vague role. `RS011` bans the literal `Manager` / `Helper` / `Util` / `Utils` suffixes; judgment catches the role-not-a-thing miss those four words cannot enumerate — a `Processor` or `Coordinator` that names what a class loosely does. A class whose best name is a verb usually wants to be a function.
- **Booleans read as a positive yes/no question** — `is_` / `has_` / `can_` / `should_`. `RS024` mechanically rejects an embedded `not` / `no` word, and `RS026` requires the prefix on a `bool`-annotated name; judgment catches what neither reaches — a bool that reads negative through a prefix-merged word (`is_invalid`, forcing `if not is_invalid` → `is_valid`) or a `bool`-returning function or property not phrased as a question at all (`valid()` → `is_valid()`), whose return type the annotation match in `RS026` does not see.
- **Clarity beats brevity.** This codebase is verbose on purpose; a longer name that removes a guess wins. `RS010` owns the fixed abbreviation list; judgment catches the wide-scope, too-terse name it cannot pre-enumerate — a module-level `data`, `tmp`, `val`, or a single-letter non-loop variable that forces the reader to reconstruct intent.

## E. Tests pin contract, not implementation

The disciplined question for every assertion: *if a refactor preserves the behavior the user actually relies on, would this assertion still pass?* If no, it pins implementation. The mechanical test smells are gated (`RS013`–`RS016`); this is the semantic residue those token checks cannot see.

- **Verbatim message-layout pinning** — a `match=` regex or `str(exc) ==` pinning a message's *layout* (word order, separators) instead of the *fields* it must surface. A single load-bearing identifier (`match=r"access_token"`) is fine; the smell is a multi-token regex mirroring an `f"…"` line.
- **Constant pinning** — an assertion equal to a constant defined next to the code under test; it fails only if someone edits both sides at once, which is not a realistic regression.
- **Constant-coupled numerics** — a hardcoded number justified as "greater than `<magic constant in source>`". Import the constant and test the boundary, or rename the test to the looser guarantee it defends.
- **Incidental call-count** — `assert spy.call_count == 3` where 3 is incidental. Acceptable only when the count *is* the contract ("a 5-item page deduped to 1 request").

Prefer asserting the fields a message must surface over its exact layout: `for sub in ["401", "invalid_client"]: assert sub in str(exc.value)` survives a formatter refactor that `match=r"401 invalid_client: …"` does not.

## F. Prose stays accurate after edits

The most common find on a polished branch is a docstring or comment a later edit left stale. Cross-reference each changed docstring against the *current* signature and body, not what it said before.

- A concept an earlier edit renamed, now wrong in a docstring that still uses the old name.
- A behavior a fix subtly changed, now mis-described by prose written before the fix.
- An `Args:` or `Returns:` line describing a parameter or return the signature no longer has.

## Using this canon

- **Repos** reference this doc from their `CLAUDE.md` style section rather than restating the conventions, so the canon has one home. Repo-specific conventions (a hexagonal `ports` layer, a test-naming scheme) stay in that repo's docs; what lives here applies across repos.
- **Reviewers** — human or agent — cite this doc as the source of truth rather than restating a convention in a comment thread.
- **Graduation** is one-directional: a judgment convention that becomes mechanically decidable moves to an `RSnnn` rule and is struck from this doc, with a pointer left behind (as `make_` and the negated boolean were). This doc only ever shrinks as the linter grows.
